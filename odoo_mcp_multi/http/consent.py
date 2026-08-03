"""The Odoo consent screen and the extra well-known routes.

These are the only endpoints a human ever sees. They are deliberately exempt
from bearer authentication — the whole point is that the caller has no token
yet — so everything they accept is validated here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import anyio
import jinja2
from pydantic import SecretStr, ValidationError
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from odoo_mcp_multi.config import OdooProfile
from odoo_mcp_multi.http.provider import MAX_LOGIN_ATTEMPTS, OdooOAuthProvider
from odoo_mcp_multi.http.settings import DEFAULT_SCOPES, HttpServeConfig
from odoo_mcp_multi.operations import op_list_databases, op_validate_credentials
from odoo_mcp_multi.parsers import normalize_url
from odoo_mcp_multi.server import SERVER_NAME

_TEMPLATES = jinja2.Environment(
    loader=jinja2.FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=True,
    undefined=jinja2.ChainableUndefined,
)

# Odoo can take a while to answer a first authentication; well past this and
# the user is better served by an error than by a hanging page.
LOGIN_TIMEOUT_SECONDS = 30


def render(template: str, **context: Any) -> str:
    """Render one of the bundled HTML templates."""
    return _TEMPLATES.get_template(template).render(server_name=SERVER_NAME, **context)


def _error_page(title: str, message: str, next_step: str, status: int) -> HTMLResponse:
    return HTMLResponse(
        render("error.html", title=title, message=message, next_step=next_step),
        status_code=status,
    )


def _host_allowed(url: str, config: HttpServeConfig) -> bool:
    """Check a user-supplied Odoo URL against the operator's allow-list.

    The consent form is unauthenticated and dials arbitrary URLs, which makes
    it an SSRF pivot into whatever network the server sits on unless the
    operator bounds it.
    """
    if not config.allowed_odoo_hosts:
        return True
    host = (urlparse(normalize_url(url)).hostname or "").lower()
    return any(
        host == allowed.lower() or host.endswith("." + allowed.lower()) for allowed in config.allowed_odoo_hosts
    )


class ConsentRoutes:
    """Handlers for the consent form, bound to one server configuration."""

    def __init__(self, config: HttpServeConfig, provider: OdooOAuthProvider) -> None:
        self.config = config
        self.provider = provider

    # -- GET /odoo/login ---------------------------------------------------

    async def login_form(self, request: Request) -> Response:
        """Show the credential form for a pending authorization request."""
        txn_id = request.query_params.get("txn", "")
        txn = self.provider.store.get_txn(txn_id) if txn_id else None
        if txn is None:
            return _error_page(
                "This link has expired",
                "The authorization request behind this page is no longer valid.",
                "Go back to your MCP client and connect again.",
                400,
            )
        return HTMLResponse(self._render_form(txn))

    # -- POST /odoo/login --------------------------------------------------

    async def login_submit(self, request: Request) -> Response:
        """Validate the credentials against Odoo and issue the code."""
        form = await request.form()
        txn_id = str(form.get("txn", ""))
        txn = self.provider.store.get_txn(txn_id) if txn_id else None
        if txn is None:
            return _error_page(
                "This link has expired",
                "The authorization request behind this page is no longer valid.",
                "Go back to your MCP client and connect again.",
                400,
            )

        submitted = {
            "odoo_url": str(form.get("odoo_url", "")).strip(),
            "database": str(form.get("database", "")).strip(),
            "login": str(form.get("login", "")).strip(),
            "secret_kind": str(form.get("secret_kind", "api_key")),
            "protocol": str(form.get("protocol", "auto")),
        }
        secret = str(form.get("secret", ""))

        if not all((submitted["odoo_url"], submitted["database"], submitted["login"], secret)):
            return self._retry(txn, submitted, "Every field is required.")

        if not _host_allowed(submitted["odoo_url"], self.config):
            return self._retry(
                txn,
                submitted,
                "This server is not allowed to connect to that host. "
                f"Allowed: {', '.join(self.config.allowed_odoo_hosts)}.",
            )

        is_api_key = submitted["secret_kind"] != "password"
        try:
            profile = OdooProfile(
                name=f"oauth:{submitted['database']}",
                url=normalize_url(submitted["odoo_url"]),
                database=submitted["database"],
                user=submitted["login"],
                password=None if is_api_key else SecretStr(secret),
                api_key=SecretStr(secret) if is_api_key else None,
                protocol=submitted["protocol"] or "auto",
            )
        except ValidationError as exc:
            return self._retry(txn, submitted, f"Those details are not usable: {exc.errors()[0]['msg']}")

        result = await anyio.to_thread.run_sync(
            lambda: op_validate_credentials(
                url=profile.url,
                database=profile.database,
                user=profile.user,
                password=secret if not is_api_key else "",
                api_key=secret if is_api_key else "",
                protocol=profile.protocol,
                timeout=LOGIN_TIMEOUT_SECONDS,
                verify=profile.verify,
            )
        )

        if not result.get("success"):
            attempts = self.provider.store.bump_txn_attempts(txn_id, MAX_LOGIN_ATTEMPTS)
            if attempts >= MAX_LOGIN_ATTEMPTS:
                return _error_page(
                    "Too many attempts",
                    "This authorization request was cancelled after too many failed sign-ins.",
                    "Go back to your MCP client and connect again.",
                    429,
                )
            return self._retry(txn, submitted, result.get("error", "Odoo rejected those credentials."))

        # Persist the resolved protocol so no tool call ever pays for
        # auto-detection again.
        resolved = result.get("protocol") or "auto"
        if resolved and resolved != "auto":
            profile = profile.model_copy(update={"protocol": resolved})

        redirect_to = self.provider.complete_login(txn, profile, result.get("uid"))
        return RedirectResponse(redirect_to, status_code=302)

    # -- POST /odoo/databases ---------------------------------------------

    async def databases(self, request: Request) -> Response:
        """Best-effort database list for the form's datalist.

        Most production instances run with ``list_db = False``, so an empty
        result is the normal case rather than a failure.
        """
        try:
            payload = await request.json()
        except (json.JSONDecodeError, ValueError):
            return JSONResponse({"databases": []})

        url = str(payload.get("odoo_url", "")).strip()
        if not url or not _host_allowed(url, self.config):
            return JSONResponse({"databases": []})

        result = await anyio.to_thread.run_sync(lambda: op_list_databases(normalize_url(url)))
        return JSONResponse({"databases": result.get("databases", [])})

    # -- GET /.well-known/oauth-protected-resource -------------------------

    async def bare_protected_resource(self, request: Request) -> Response:
        """Serve the RFC 9728 document at the path-less well-known location.

        The SDK only mounts it under the resource path. Some clients probe the
        bare path first, so answering both costs nothing and removes a
        discovery failure mode that surfaces as "couldn't reach the server".
        """
        return JSONResponse(
            {
                "resource": self.config.resource_url,
                "authorization_servers": [self.config.issuer_url],
                "scopes_supported": list(DEFAULT_SCOPES),
                "bearer_methods_supported": ["header"],
            }
        )

    # -- GET /health -------------------------------------------------------

    async def health(self, request: Request) -> Response:
        """Liveness probe that never touches Odoo."""
        return JSONResponse({"status": "ok", "resource": self.config.resource_url})

    # -- internals ---------------------------------------------------------

    def _render_form(
        self,
        txn: dict[str, Any],
        form: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> str:
        client = self.provider.store.get_client(txn["client_id"]) or {}
        params = json.loads(txn["params_json"])
        return render(
            "login.html",
            action=f"{self.config.issuer_url}/odoo/login",
            txn=txn["txn_id"],
            client_name=client.get("client_name") or txn["client_id"],
            client_uri=client.get("client_uri") or "",
            scopes=params.get("scopes") or list(DEFAULT_SCOPES),
            allowed_hosts=list(self.config.allowed_odoo_hosts),
            databases=[],
            form=form or {},
            error=error,
        )

    def _retry(self, txn: dict[str, Any], form: dict[str, Any], error: str) -> HTMLResponse:
        """Re-render the form with the failure, without minting anything."""
        return HTMLResponse(self._render_form(txn, form=form, error=error), status_code=200)

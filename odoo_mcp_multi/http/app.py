"""Assemble the Starlette application served by ``odoo-mcp serve``.

Three settings here are not preferences but requirements, each learned from
reading the SDK rather than its docs:

* ``stateless_http=True``. In stateful mode the MCP session task is spawned
  during the *initialize* request, and every later tool call runs inside that
  first request's context. The authenticated identity would then be whoever
  opened the session, so a stolen session id would execute with someone
  else's Odoo credentials. Stateless mode spawns the task per request.
* An explicit ``TransportSecuritySettings``. FastMCP turns on DNS-rebinding
  protection whenever it binds a loopback address, allowing only loopback
  Host headers. Behind a reverse proxy the Host is the public name, so every
  request would be rejected with 421 before reaching any handler.
* ``json_response=True``. Every tool here is a plain request/response, and
  buffering proxies are a recurring source of trouble for event streams.
"""

from __future__ import annotations

from typing import Optional

import anyio
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette

from odoo_mcp_multi import operations
from odoo_mcp_multi.http.consent import ConsentRoutes
from odoo_mcp_multi.http.crypto import CredentialCipher
from odoo_mcp_multi.http.provider import OdooOAuthProvider
from odoo_mcp_multi.http.settings import CLAUDE_REDIRECT_URI, DEFAULT_SCOPES, HttpServeConfig
from odoo_mcp_multi.http.store import AuthStore
from odoo_mcp_multi.server import build_server


def build_auth_settings(config: HttpServeConfig) -> AuthSettings:
    """Derive the SDK's auth settings from the public URL."""
    return AuthSettings(
        issuer_url=AnyHttpUrl(config.issuer_url),
        resource_server_url=AnyHttpUrl(config.resource_url),
        required_scopes=list(DEFAULT_SCOPES),
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=list(DEFAULT_SCOPES),
            default_scopes=list(DEFAULT_SCOPES),
        ),
        revocation_options=RevocationOptions(enabled=True),
    )


def build_transport_security(config: HttpServeConfig) -> TransportSecuritySettings:
    """Allow the public hostname through the DNS-rebinding guard."""
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[config.netloc, f"{config.host}:{config.port}", "127.0.0.1:*", "localhost:*"],
        allowed_origins=[config.issuer_url, "https://claude.ai", CLAUDE_REDIRECT_URI.rsplit("/api", 1)[0]],
    )


def build_mcp_server(config: HttpServeConfig, provider: Optional[OdooOAuthProvider]) -> FastMCP:
    """Build the FastMCP instance backing the HTTP transport."""
    kwargs = {
        "host": config.host,
        "port": config.port,
        "streamable_http_path": config.path,
        "json_response": config.json_response,
        "stateless_http": config.stateless,
        "transport_security": build_transport_security(config),
        "log_level": config.log_level,
    }
    if provider is not None:
        kwargs["auth_server_provider"] = provider
        kwargs["auth"] = build_auth_settings(config)
    return build_server(**kwargs)


def build_http_app(config: HttpServeConfig) -> Starlette:
    """Build the ASGI application for one ``odoo-mcp serve`` process."""
    config.validate_runtime()

    # Bound how long a stalled Odoo call can hold a worker thread, and how
    # many can be in flight at once. The OAuth endpoints never take a thread,
    # so they stay responsive even when every Odoo call is stuck.
    operations.set_default_timeout(config.odoo_timeout)

    provider: Optional[OdooOAuthProvider] = None
    consent: Optional[ConsentRoutes] = None
    if config.auth_enabled:
        store = AuthStore(config.state_db, CredentialCipher.from_file(config.secret_key_file))
        provider = OdooOAuthProvider(config, store)
        consent = ConsentRoutes(config, provider)

    server = build_mcp_server(config, provider)

    if consent is not None:
        # Custom routes are exempt from bearer auth by design, which is what
        # the consent flow and the discovery documents need.
        server.custom_route("/odoo/login", methods=["GET"])(consent.login_form)
        server.custom_route("/odoo/login", methods=["POST"])(consent.login_submit)
        server.custom_route("/odoo/databases", methods=["POST"])(consent.databases)
        server.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])(consent.bare_protected_resource)
        server.custom_route("/health", methods=["GET"])(consent.health)

    app = server.streamable_http_app()
    app.add_middleware(ThreadLimitMiddleware, max_concurrency=config.max_concurrency)
    return app


class ThreadLimitMiddleware:
    """Size the worker pool that serves blocking Odoo calls.

    anyio's default thread limiter belongs to the running event loop, which
    only exists once the server starts, so the size is applied on the first
    message the application receives — the lifespan startup — rather than at
    build time.
    """

    def __init__(self, app, max_concurrency: int) -> None:
        self.app = app
        self.max_concurrency = max_concurrency
        self._applied = False

    async def __call__(self, scope, receive, send) -> None:
        if not self._applied:
            self._applied = True
            anyio.to_thread.current_default_thread_limiter().total_tokens = self.max_concurrency
        await self.app(scope, receive, send)

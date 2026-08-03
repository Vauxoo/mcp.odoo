"""OAuth 2.1 authorization server backed by Odoo logins.

The MCP server is its own authorization server, and the identity it
authenticates is an Odoo user: the consent screen asks for an instance, a
database and a credential, verifies them against that Odoo, and binds the
issued tokens to them. Every later tool call therefore runs as that user,
under their own access rights, and the host's ``profiles.json`` is never
consulted.

Two details of the SDK shape this module:

* ``load_access_token`` returns the object the auth middleware stores in a
  context variable, so attaching the resolved :class:`OdooProfile` to an
  ``AccessToken`` subclass is all it takes to reach the tool layer.
* ``OAuthClientMetadata.validate_redirect_uri`` requires exact membership,
  which would reject the ephemeral loopback port native clients use. The
  client wrapper below relaxes that for loopback addresses only.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional
from urllib.parse import urlparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import InvalidRedirectUriError, OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from odoo_mcp_multi.config import OdooProfile
from odoo_mcp_multi.http.settings import (
    DEFAULT_AUTH_CODE_TTL,
    DEFAULT_SCOPES,
    DEFAULT_TXN_TTL,
    HttpServeConfig,
)
from odoo_mcp_multi.http.store import AuthStore

# A consent form that talks to an arbitrary Odoo is also a password oracle if
# it can be retried forever; this bounds it per transaction.
MAX_LOGIN_ATTEMPTS = 5


class OdooAccessToken(AccessToken):
    """Access token carrying the Odoo credentials it was issued for."""

    grant_id: str
    credential_id: str
    odoo_profile: Optional[OdooProfile] = None


class OdooRefreshToken(RefreshToken):
    """Refresh token tied to the grant whose chain it can rotate."""

    grant_id: str


class OdooAuthorizationCode(AuthorizationCode):
    """Authorization code remembering which credentials it was minted from."""

    credential_id: str


class LoopbackClientInformation(OAuthClientInformationFull):
    """Client registration that accepts loopback redirects on any port.

    RFC 8252 §7.3 requires authorization servers to ignore the port of a
    loopback redirect URI, because native clients bind an ephemeral one. The
    base model compares URIs exactly, so a native MCP client would never get
    past ``/authorize``. Non-loopback hosts keep the strict comparison.
    """

    def validate_redirect_uri(self, redirect_uri: AnyUrl | None) -> AnyUrl:
        if redirect_uri is not None and self.redirect_uris:
            for registered in self.redirect_uris:
                if _loopback_match(registered, redirect_uri):
                    # Return what was asked for, not the registered template:
                    # the token endpoint compares this against the redirect_uri
                    # replayed in the token request.
                    return redirect_uri
        return super().validate_redirect_uri(redirect_uri)


def _loopback_match(registered: AnyUrl, requested: AnyUrl) -> bool:
    """Return True if two URIs match ignoring the port, on loopback only."""
    reg = urlparse(str(registered))
    req = urlparse(str(requested))
    if reg.hostname not in ("localhost", "127.0.0.1", "::1"):
        return False
    return reg.scheme == req.scheme and reg.hostname == req.hostname and (reg.path or "/") == (req.path or "/")


class OdooOAuthProvider:
    """Authorization server whose user authentication happens against Odoo."""

    def __init__(self, config: HttpServeConfig, store: AuthStore) -> None:
        self.config = config
        self.store = store

    # -- client registration ----------------------------------------------

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Persist a dynamically registered client."""
        for uri in client_info.redirect_uris or []:
            parsed = urlparse(str(uri))
            if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                raise RegistrationError(
                    error="invalid_redirect_uri",
                    error_description=f"Redirect URI '{uri}' must use https or a loopback address.",
                )
        self.store.put_client(
            client_info.client_id,
            json.loads(client_info.model_dump_json(exclude_none=True)),
            client_name=client_info.client_name or "",
        )

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Load a registered client, relaxing loopback redirect matching."""
        data = self.store.get_client(client_id)
        if data is None:
            return None
        try:
            return LoopbackClientInformation.model_validate(data)
        except ValueError:
            return None

    # -- authorization -----------------------------------------------------

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Park the request and send the user to the Odoo consent form.

        No Odoo call happens here — the user has not told us which instance
        they want yet. The request parameters are stored under an opaque
        transaction id that the consent form hands back.
        """
        scopes = params.scopes or list(DEFAULT_SCOPES)
        unknown = [s for s in scopes if s not in DEFAULT_SCOPES]
        if unknown:
            raise AuthorizeError(error="invalid_scope", error_description=f"Unknown scopes: {unknown}")

        payload = json.loads(params.model_dump_json())
        payload["scopes"] = scopes
        txn_id = self.store.put_txn(client.client_id, json.dumps(payload), ttl=DEFAULT_TXN_TTL)
        return f"{self.config.login_url}?txn={txn_id}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> OdooAuthorizationCode | None:
        """Read a pending authorization code without consuming it."""
        row = self.store.peek_code(authorization_code, client.client_id)
        return _row_to_code(row) if row else None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: OdooAuthorizationCode
    ) -> OAuthToken:
        """Redeem a code once and open a grant for the credentials behind it."""
        self.store.maybe_purge()
        row = self.store.consume_code(authorization_code.code, client.client_id)
        if row is None:
            raise TokenError(
                error="invalid_grant",
                error_description="Authorization code has already been used or has expired.",
            )

        scopes = row["scopes"].split() if row["scopes"] else list(DEFAULT_SCOPES)
        grant_id = self.store.create_grant(
            client_id=client.client_id,
            credential_id=row["credential_id"],
            scopes=scopes,
            resource=row["resource"],
        )
        return self._issue(grant_id, scopes)

    # -- refresh -----------------------------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> OdooRefreshToken | None:
        """Read a refresh token and the grant it belongs to."""
        row = self.store.get_refresh_token(refresh_token)
        if row is None or row["client_id"] != client.client_id:
            return None
        return OdooRefreshToken(
            token=refresh_token,
            client_id=row["client_id"],
            scopes=row["scopes"].split() if row["scopes"] else [],
            expires_at=int(row["expires_at"]) if row["expires_at"] else None,
            grant_id=row["grant_id"],
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: OdooRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """Rotate the refresh token, retiring the previous chain.

        A replayed refresh token must fail with ``invalid_grant`` — anything
        else makes clients retry forever instead of re-authorizing.
        """
        if not self.store.rotate_refresh_token(refresh_token.token):
            raise TokenError(
                error="invalid_grant",
                error_description="Refresh token has already been used or was revoked.",
            )
        granted = scopes or refresh_token.scopes or list(DEFAULT_SCOPES)
        return self._issue(refresh_token.grant_id, granted)

    # -- resource server side ---------------------------------------------

    async def load_access_token(self, token: str) -> OdooAccessToken | None:
        """Resolve a bearer token into an identity and its Odoo credentials.

        Must never raise: Starlette turns an authentication exception into a
        400, while MCP clients only start the OAuth dance on a 401.
        """
        try:
            self.store.maybe_purge()
            row = self.store.get_access_token(token)
            if row is None:
                return None

            profile_dict = self.store.get_credential(row["credential_id"])
            if profile_dict is None:
                return None
            profile = OdooProfile.from_dict(profile_dict)
            self.store.touch_credential(row["credential_id"])

            return OdooAccessToken(
                token=token,
                client_id=row["client_id"],
                scopes=row["scopes"].split() if row["scopes"] else [],
                expires_at=int(row["expires_at"]),
                resource=row["resource"],
                subject=f"{profile.url}#{profile.user or profile.database}",
                grant_id=row["grant_id"],
                credential_id=row["credential_id"],
                odoo_profile=profile,
            )
        except Exception:
            return None

    async def verify_token(self, token: str) -> OdooAccessToken | None:
        """TokenVerifier protocol — same lookup as :meth:`load_access_token`."""
        return await self.load_access_token(token)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """Revoke a whole grant, including the stored Odoo credentials."""
        grant_id = getattr(token, "grant_id", None)
        if grant_id:
            self.store.revoke_grant(grant_id)

    # -- consent form support ---------------------------------------------

    def complete_login(
        self,
        txn: dict[str, Any],
        profile: OdooProfile,
        uid: Optional[int],
    ) -> str:
        """Store validated credentials and mint the authorization code.

        Returns the redirect URI, with ``code`` and ``state`` attached, that
        sends the user back to their MCP client.
        """
        params = json.loads(txn["params_json"])
        # to_dict() unwraps the SecretStr fields; model_dump would persist the
        # masked placeholder and silently lose the credential.
        credential_id = self.store.put_credential(profile.to_dict(), uid)
        code = self.store.put_code(
            client_id=txn["client_id"],
            scopes=params.get("scopes") or list(DEFAULT_SCOPES),
            code_challenge=params["code_challenge"],
            redirect_uri=params["redirect_uri"],
            redirect_uri_provided_explicitly=bool(params["redirect_uri_provided_explicitly"]),
            resource=params.get("resource"),
            credential_id=credential_id,
            ttl=DEFAULT_AUTH_CODE_TTL,
        )
        self.store.delete_txn(txn["txn_id"])
        return construct_redirect_uri(params["redirect_uri"], code=code, state=params.get("state"))

    # -- internals ---------------------------------------------------------

    def _issue(self, grant_id: str, scopes: list[str]) -> OAuthToken:
        """Mint an access/refresh pair for a grant."""
        access_token, expires_at = self.store.put_access_token(grant_id, self.config.access_token_ttl)
        refresh_token = self.store.put_refresh_token(grant_id, self.config.refresh_token_ttl)
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=int(expires_at - time.time()),
            scope=" ".join(scopes),
            refresh_token=refresh_token,
        )


def _row_to_code(row: dict[str, Any]) -> OdooAuthorizationCode:
    """Rebuild an authorization code from its stored row."""
    return OdooAuthorizationCode(
        code=row["code"],
        scopes=row["scopes"].split() if row["scopes"] else [],
        expires_at=float(row["expires_at"]),
        client_id=row["client_id"],
        code_challenge=row["code_challenge"],
        redirect_uri=AnyUrl(row["redirect_uri"]),
        redirect_uri_provided_explicitly=bool(row["redirect_uri_provided_explicitly"]),
        resource=row["resource"],
        credential_id=row["credential_id"],
    )


__all__ = [
    "InvalidRedirectUriError",
    "LoopbackClientInformation",
    "MAX_LOGIN_ATTEMPTS",
    "OdooAccessToken",
    "OdooAuthorizationCode",
    "OdooOAuthProvider",
    "OdooRefreshToken",
]

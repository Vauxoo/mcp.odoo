"""Accept client credentials sent the way RFC 6749 §2.3.1 describes.

A client registered with ``client_secret_basic`` puts its identifier and
secret in an ``Authorization: Basic`` header and is not required to repeat
either in the request body. The SDK's client authenticator reads ``client_id``
from the form first and rejects the request with "Missing client_id" before it
ever looks at the header, so those clients fail at the token endpoint with a
401 — after the user has already signed in and an authorization code has been
issued, which makes it look like the credentials were rejected.

This middleware copies the header credentials into the form body when they are
absent, so the authenticator finds what it expects. It never overwrites values
the client did send, so a mismatch between header and body still fails the
SDK's own comparison.
"""

from __future__ import annotations

import base64
import binascii
from urllib.parse import parse_qsl, unquote, urlencode

# The SDK mounts both of these at the application root.
CLIENT_AUTH_PATHS = frozenset({"/token", "/revoke"})

FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"


def _decode_basic(header: str) -> tuple[str, str] | None:
    """Return the (client_id, client_secret) carried by a Basic header."""
    if not header.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(header[6:]).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if ":" not in decoded:
        return None
    client_id, client_secret = decoded.split(":", 1)
    # Both halves are form-encoded per RFC 6749 §2.3.1.
    return unquote(client_id), unquote(client_secret)


class BasicClientAuthMiddleware:
    """Back-fill Basic credentials into the form body of OAuth endpoints."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if not self._applies(scope):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        credentials = _decode_basic(headers.get("authorization", ""))
        if credentials is None:
            await self.app(scope, receive, send)
            return

        body = await _read_body(receive)
        patched = _merge_credentials(body, *credentials)
        if patched == body:
            await self.app(scope, _replay(body), send)
            return

        scope = dict(scope)
        scope["headers"] = _with_content_length(scope["headers"], len(patched))
        await self.app(scope, _replay(patched), send)

    @staticmethod
    def _applies(scope) -> bool:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            return False
        if scope.get("path") not in CLIENT_AUTH_PATHS:
            return False
        content_type = next(
            (
                v.decode("latin-1")
                for k, v in scope.get("headers", [])
                if k.decode("latin-1").lower() == "content-type"
            ),
            "",
        )
        return content_type.split(";")[0].strip() == FORM_CONTENT_TYPE


def _merge_credentials(body: bytes, client_id: str, client_secret: str) -> bytes:
    """Add the header credentials to a form body that omits them."""
    try:
        fields = parse_qsl(body.decode("utf-8"), keep_blank_values=True)
    except UnicodeDecodeError:
        return body

    present = {key for key, _ in fields}
    if "client_id" in present and "client_secret" in present:
        return body

    if "client_id" not in present:
        fields.append(("client_id", client_id))
    if "client_secret" not in present:
        fields.append(("client_secret", client_secret))
    return urlencode(fields).encode("utf-8")


async def _read_body(receive) -> bytes:
    """Drain an ASGI request body."""
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay(body: bytes):
    """Return a receive callable that yields ``body`` once."""
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _with_content_length(headers, length: int):
    """Return ASGI headers with content-length set to ``length``."""
    patched = [(k, v) for k, v in headers if k.decode("latin-1").lower() != "content-length"]
    patched.append((b"content-length", str(length).encode("latin-1")))
    return patched

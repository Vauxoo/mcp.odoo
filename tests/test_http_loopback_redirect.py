"""Loopback redirect URIs must ignore the port — and only the port.

Native MCP clients bind an ephemeral loopback port and register a portless
template, so RFC 8252 §7.3 requires the authorization server to compare
loopback redirects without the port. Relaxing that comparison anywhere else
would be an open redirect, so the negative cases are the point of this file.
"""

from __future__ import annotations

import pytest
from pydantic import AnyUrl

from odoo_mcp_multi.http.provider import LoopbackClientInformation
from tests.test_http_oauth_flow import CLAUDE_REDIRECT, authorize, consent, exchange, pkce, register

NATIVE_REDIRECTS = ("http://localhost/callback", "http://127.0.0.1/callback")


def _client_info(redirect_uris):
    return LoopbackClientInformation(
        client_id="native",
        redirect_uris=[AnyUrl(uri) for uri in redirect_uris],
        client_name="Native client",
    )


@pytest.mark.parametrize(
    "requested",
    [
        "http://127.0.0.1:54321/callback",
        "http://127.0.0.1:1/callback",
        "http://localhost:8765/callback",
        "http://localhost/callback",
    ],
)
def test_loopback_ports_are_accepted(requested):
    """Any port on a registered loopback host is acceptable."""
    info = _client_info(NATIVE_REDIRECTS)
    assert str(info.validate_redirect_uri(AnyUrl(requested))) == requested


@pytest.mark.parametrize(
    "requested",
    [
        "http://evil.com/callback",
        "http://localhost:54321/other",
        "https://claude.ai.evil.com/api/mcp/auth_callback",
        "http://127.0.0.1.evil.com/callback",
    ],
)
def test_non_matching_redirects_are_rejected(requested):
    """Everything else keeps the strict comparison."""
    info = _client_info(NATIVE_REDIRECTS)
    with pytest.raises(Exception) as excinfo:
        info.validate_redirect_uri(AnyUrl(requested))
    assert "not registered" in str(excinfo.value)


def test_port_agnostism_does_not_apply_to_public_hosts():
    """A registered https host must still match its port exactly."""
    info = _client_info([CLAUDE_REDIRECT])
    with pytest.raises(Exception):
        info.validate_redirect_uri(AnyUrl("https://claude.ai:8443/api/mcp/auth_callback"))


async def test_native_client_completes_the_flow_on_an_ephemeral_port(client):
    """The token exchange must accept the same ported URI it redirected to."""
    registration = await register(client, redirect_uris=NATIVE_REDIRECTS, name="Native")
    ephemeral = "http://127.0.0.1:54321/callback"

    verifier, challenge = pkce()
    txn = await authorize(client, registration["client_id"], challenge, redirect_uri=ephemeral)

    consented = await consent(client, txn)
    assert consented.status_code == 302
    assert consented.headers["location"].startswith(ephemeral)

    from urllib.parse import parse_qs, urlparse

    code = parse_qs(urlparse(consented.headers["location"]).query)["code"][0]
    tokens = await exchange(client, registration, code, verifier, redirect_uri=ephemeral)
    assert tokens.status_code == 200, tokens.text
    assert tokens.json()["access_token"]


async def test_registration_rejects_plaintext_public_redirects(client):
    """A non-loopback http redirect would leak the code in transit."""
    response = await client.post(
        "/register",
        json={
            "client_name": "Sketchy",
            "redirect_uris": ["http://example.com/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"

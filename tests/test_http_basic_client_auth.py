"""Clients that authenticate with HTTP Basic must reach the token endpoint.

Registering with ``client_secret_basic`` and then sending the credentials in
an ``Authorization`` header is what RFC 6749 §2.3.1 describes, and what some
MCP clients do — Gemini among them. The SDK's client authenticator reads
``client_id`` from the form body before it looks at the header, so those
clients were rejected with "Missing client_id" *after* the user had already
signed in and an authorization code had been issued.

That is the worst shape a failure can take: everything the user sees succeeds,
and the connection dies on the last server-to-server call.
"""

from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlparse

import pytest

from tests.test_http_oauth_flow import authorize, consent, pkce

# The redirect Google registers for a custom MCP connector.
GOOGLE_REDIRECT = "https://oauth-redirect.googleusercontent.com/r/user_bound_custom-mcp-1-odoo"


def basic_header(client_id: str, client_secret: str) -> str:
    return "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()


async def register_basic(client, redirect_uri: str = GOOGLE_REDIRECT):
    """Register the way a client_secret_basic client does."""
    response = await client.post(
        "/register",
        json={
            "client_name": "Google",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_basic",
        },
    )
    assert response.status_code == 201, response.text
    registration = response.json()
    assert registration["token_endpoint_auth_method"] == "client_secret_basic"
    return registration


async def test_metadata_advertises_basic(client):
    """The server tells clients Basic is acceptable, so it must accept it."""
    doc = (await client.get("/.well-known/oauth-authorization-server")).json()
    assert "client_secret_basic" in doc["token_endpoint_auth_methods_supported"]


async def test_full_flow_with_basic_authentication(client):
    """The whole dance, with credentials only ever in the header."""
    registration = await register_basic(client)
    verifier, challenge = pkce()
    txn = await authorize(client, registration["client_id"], challenge, redirect_uri=GOOGLE_REDIRECT)

    redirected = await consent(client, txn)
    assert redirected.status_code == 302, redirected.text
    code = parse_qs(urlparse(redirected.headers["location"]).query)["code"][0]

    tokens = await client.post(
        "/token",
        headers={"Authorization": basic_header(registration["client_id"], registration["client_secret"])},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": GOOGLE_REDIRECT,
            "code_verifier": verifier,
        },
    )
    assert tokens.status_code == 200, tokens.text
    body = tokens.json()
    assert body["access_token"]
    assert body["refresh_token"]

    refreshed = await client.post(
        "/token",
        headers={"Authorization": basic_header(registration["client_id"], registration["client_secret"])},
        data={"grant_type": "refresh_token", "refresh_token": body["refresh_token"]},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["access_token"] != body["access_token"]


async def test_a_wrong_secret_in_the_header_is_still_rejected(client):
    """Back-filling credentials must not weaken the check."""
    registration = await register_basic(client)
    verifier, challenge = pkce()
    txn = await authorize(client, registration["client_id"], challenge, redirect_uri=GOOGLE_REDIRECT)
    redirected = await consent(client, txn)
    code = parse_qs(urlparse(redirected.headers["location"]).query)["code"][0]

    tokens = await client.post(
        "/token",
        headers={"Authorization": basic_header(registration["client_id"], "not-the-secret")},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": GOOGLE_REDIRECT,
            "code_verifier": verifier,
        },
    )
    assert tokens.status_code == 401


async def test_an_unknown_client_in_the_header_is_rejected(client):
    """A header naming a client that was never registered gets nowhere."""
    tokens = await client.post(
        "/token",
        headers={"Authorization": basic_header("no-such-client", "whatever")},
        data={"grant_type": "authorization_code", "code": "x", "redirect_uri": GOOGLE_REDIRECT},
    )
    assert tokens.status_code == 401


async def test_a_mismatched_identity_between_header_and_body_is_rejected(client):
    """The header cannot be used to act as a client the body does not name.

    Back-filling must not let one identity be smuggled past a request whose
    body claims another. The SDK compares the two and refuses; this pins that
    the middleware leaves a body-supplied `client_id` alone so the comparison
    still happens.
    """
    victim = await register_basic(client)
    attacker = await register_basic(client, redirect_uri="https://attacker.example.com/cb")

    tokens = await client.post(
        "/token",
        headers={"Authorization": basic_header(attacker["client_id"], attacker["client_secret"])},
        data={
            "grant_type": "authorization_code",
            "code": "irrelevant",
            "redirect_uri": GOOGLE_REDIRECT,
            "client_id": victim["client_id"],
        },
    )
    assert tokens.status_code == 401


async def test_the_header_secret_is_still_checked_when_the_body_repeats_the_id(client):
    """A correct id in the body does not excuse a wrong secret in the header."""
    registration = await register_basic(client)
    tokens = await client.post(
        "/token",
        headers={"Authorization": basic_header(registration["client_id"], "wrong-on-purpose")},
        data={
            "grant_type": "authorization_code",
            "code": "irrelevant",
            "redirect_uri": GOOGLE_REDIRECT,
            "client_id": registration["client_id"],
        },
    )
    assert tokens.status_code == 401


# -- unit level -------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b"grant_type=authorization_code", {"grant_type", "client_id", "client_secret"}),
        (b"grant_type=x&client_id=given", {"grant_type", "client_id", "client_secret"}),
        (b"grant_type=x&client_id=given&client_secret=given", {"grant_type", "client_id", "client_secret"}),
    ],
)
def test_merge_only_fills_what_is_missing(body, expected):
    from odoo_mcp_multi.http.basic_auth import _merge_credentials

    merged = _merge_credentials(body, "from-header", "secret-from-header")
    fields = parse_qs(merged.decode())
    assert set(fields) == expected

    if b"client_id=given" in body:
        assert fields["client_id"] == ["given"]
    else:
        assert fields["client_id"] == ["from-header"]

    if b"client_secret=given" in body:
        assert fields["client_secret"] == ["given"]
    else:
        assert fields["client_secret"] == ["secret-from-header"]


@pytest.mark.parametrize(
    "header",
    ["", "Bearer abc", "Basic !!!not-base64!!!", "Basic " + base64.b64encode(b"no-colon").decode()],
)
def test_unusable_headers_are_ignored(header):
    from odoo_mcp_multi.http.basic_auth import _decode_basic

    assert _decode_basic(header) is None


def test_percent_encoded_credentials_are_decoded():
    """RFC 6749 §2.3.1 form-encodes both halves before base64."""
    from odoo_mcp_multi.http.basic_auth import _decode_basic

    raw = base64.b64encode(b"client%20id:secret%3Awith%3Acolons").decode()
    assert _decode_basic(f"Basic {raw}") == ("client id", "secret:with:colons")

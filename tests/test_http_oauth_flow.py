"""The end-to-end authorization dance, and the ways it must refuse.

Exercises exactly what a remote MCP client does: dynamic registration, a PKCE
authorization request, the Odoo consent form, the token exchange, an
authenticated tool listing, and a refresh. The negative cases matter as much
as the happy path — a replayed code or refresh token has to fail closed, and
with ``invalid_grant`` specifically, or clients retry instead of re-authorizing.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

CLAUDE_REDIRECT = "https://claude.ai/api/mcp/auth_callback"

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

GOOD_LOGIN = {
    "odoo_url": "https://odoo.example.com",
    "database": "prod",
    "login": "someone@example.com",
    "secret_kind": "api_key",
    "secret": "an-api-key",
    "protocol": "auto",
}

VALID_CREDENTIALS = {
    "success": True,
    "uid": 7,
    "login": "someone@example.com",
    "server_version": "19.0",
    "protocol": "json2s",
}


def pkce() -> tuple[str, str]:
    """Return a PKCE verifier and its S256 challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


async def register(client, redirect_uris=(CLAUDE_REDIRECT,), name="Claude"):
    """Perform dynamic client registration the way a real client does."""
    response = await client.post(
        "/register",
        json={
            "client_name": name,
            "redirect_uris": list(redirect_uris),
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def authorize(client, client_id, challenge, redirect_uri=CLAUDE_REDIRECT, state="opaque-state"):
    """Start an authorization request and return the consent transaction id."""
    response = await client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "scope": "odoo:read odoo:write",
        },
    )
    assert response.status_code in (302, 307), response.text
    location = response.headers["location"]
    assert "/odoo/login" in location, location
    return parse_qs(urlparse(location).query)["txn"][0]


async def consent(client, txn, overrides=None):
    """Submit the consent form with a mocked Odoo validation."""
    form = dict(GOOD_LOGIN, **(overrides or {}))
    form["txn"] = txn
    with patch(
        "odoo_mcp_multi.http.consent.op_validate_credentials",
        return_value=dict(VALID_CREDENTIALS),
    ):
        return await client.post("/odoo/login", data=form)


async def exchange(client, registration, code, verifier, redirect_uri=CLAUDE_REDIRECT):
    """Redeem an authorization code at the token endpoint."""
    return await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": registration["client_id"],
            "client_secret": registration.get("client_secret", ""),
            "code_verifier": verifier,
        },
    )


async def full_flow(client):
    """Run registration through token issuance; return (registration, tokens)."""
    registration = await register(client)
    verifier, challenge = pkce()
    txn = await authorize(client, registration["client_id"], challenge)

    response = await consent(client, txn)
    assert response.status_code == 302, response.text
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["state"] == ["opaque-state"], "state must be echoed verbatim"
    code = query["code"][0]

    token_response = await exchange(client, registration, code, verifier)
    assert token_response.status_code == 200, token_response.text
    return registration, token_response.json(), (code, verifier)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_registration_returns_a_client_id(client):
    registration = await register(client)
    assert registration["client_id"]
    assert CLAUDE_REDIRECT in registration["redirect_uris"]


async def test_consent_form_renders_for_a_live_transaction(client):
    registration = await register(client)
    _, challenge = pkce()
    txn = await authorize(client, registration["client_id"], challenge)

    response = await client.get("/odoo/login", params={"txn": txn})
    assert response.status_code == 200
    assert "Connect your Odoo" in response.text
    assert "Claude" in response.text, "the requesting client must be named on the form"


async def test_full_flow_issues_usable_tokens(client):
    _, tokens, _ = await full_flow(client)
    assert tokens["token_type"].lower() == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["expires_in"] > 0
    assert set(tokens["scope"].split()) == {"odoo:read", "odoo:write"}


async def test_authenticated_client_can_list_every_tool(client):
    _, tokens, _ = await full_flow(client)
    headers = dict(MCP_HEADERS, Authorization=f"Bearer {tokens['access_token']}")

    init = await client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        },
    )
    assert init.status_code == 200, init.text

    listing = await client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert listing.status_code == 200, listing.text
    names = {tool["name"] for tool in _result(listing)["tools"]}
    assert "search_read" in names
    assert "create" in names
    assert len(names) == 13


async def test_refresh_rotates_the_token_pair(client):
    registration, tokens, _ = await full_flow(client)

    response = await client.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": registration["client_id"],
            "client_secret": registration.get("client_secret", ""),
        },
    )
    assert response.status_code == 200, response.text
    refreshed = response.json()
    assert refreshed["access_token"] != tokens["access_token"]
    assert refreshed["refresh_token"] != tokens["refresh_token"]


# ---------------------------------------------------------------------------
# Failure modes that must fail closed
# ---------------------------------------------------------------------------


async def test_replaying_an_authorization_code_is_rejected(client):
    registration, _, (code, verifier) = await full_flow(client)
    response = await exchange(client, registration, code, verifier)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


async def test_replaying_a_refresh_token_is_rejected(client):
    registration, tokens, _ = await full_flow(client)
    body = {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": registration["client_id"],
        "client_secret": registration.get("client_secret", ""),
    }
    assert (await client.post("/token", data=body)).status_code == 200

    replay = await client.post("/token", data=body)
    assert replay.status_code == 400
    assert replay.json()["error"] == "invalid_grant"


async def test_rotating_a_refresh_token_invalidates_the_old_access_token(client):
    registration, tokens, _ = await full_flow(client)
    await client.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": registration["client_id"],
            "client_secret": registration.get("client_secret", ""),
        },
    )
    stale = await client.post(
        "/mcp",
        headers=dict(MCP_HEADERS, Authorization=f"Bearer {tokens['access_token']}"),
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert stale.status_code == 401


async def test_wrong_code_verifier_is_rejected(client):
    registration = await register(client)
    _, challenge = pkce()
    txn = await authorize(client, registration["client_id"], challenge)
    response = await consent(client, txn)
    code = parse_qs(urlparse(response.headers["location"]).query)["code"][0]

    bad = await exchange(client, registration, code, "a-different-verifier")
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_grant"


async def test_failed_odoo_login_mints_nothing(client, auth_store):
    registration = await register(client)
    _, challenge = pkce()
    txn = await authorize(client, registration["client_id"], challenge)

    form = dict(GOOD_LOGIN, txn=txn)
    with patch(
        "odoo_mcp_multi.http.consent.op_validate_credentials",
        return_value={"success": False, "error": "Access denied for user"},
    ):
        response = await client.post("/odoo/login", data=form)

    assert response.status_code == 200, "the form is re-rendered, not redirected"
    assert "Access denied for user" in response.text
    with auth_store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_codes").fetchone()[0] == 0


async def test_expired_transaction_is_refused(client):
    response = await client.post("/odoo/login", data=dict(GOOD_LOGIN, txn="nope"))
    assert response.status_code == 400
    assert "expired" in response.text.lower()


async def test_revocation_kills_the_session(client):
    registration, tokens, _ = await full_flow(client)
    revoke = await client.post(
        "/revoke",
        data={
            "token": tokens["access_token"],
            "client_id": registration["client_id"],
            "client_secret": registration.get("client_secret", ""),
        },
    )
    assert revoke.status_code == 200, revoke.text

    after = await client.post(
        "/mcp",
        headers=dict(MCP_HEADERS, Authorization=f"Bearer {tokens['access_token']}"),
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert after.status_code == 401


async def test_repeated_failures_cancel_the_transaction(client):
    """A consent form that can be retried forever is a password oracle."""
    registration = await register(client)
    _, challenge = pkce()
    txn = await authorize(client, registration["client_id"], challenge)

    with patch(
        "odoo_mcp_multi.http.consent.op_validate_credentials",
        return_value={"success": False, "error": "bad password"},
    ):
        statuses = [(await client.post("/odoo/login", data=dict(GOOD_LOGIN, txn=txn))).status_code for _ in range(6)]

    # Four retries show the form again, the fifth cancels, and the cancelled transaction is gone.
    assert statuses == [200, 200, 200, 200, 429, 400]


def _result(response):
    """Extract the JSON-RPC result from an MCP response body (the server answers JSON)."""
    return response.json()["result"]

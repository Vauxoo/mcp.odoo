"""Unauthenticated calls must produce a 401 that points at the metadata.

A 400 or a 403 here is not a cosmetic difference: MCP clients only start the
authorization dance on a 401 carrying ``WWW-Authenticate``. The expired-token
case specifically guards against the token lookup raising, since Starlette
turns an authentication exception into a 400.
"""

from __future__ import annotations

import time

import pytest

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"},
    },
}


async def _post_mcp(client, token: str | None = None):
    headers = dict(MCP_HEADERS)
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return await client.post("/mcp", json=INITIALIZE, headers=headers)


def _assert_challenge(response) -> None:
    assert response.status_code == 401, f"expected 401, got {response.status_code}"
    challenge = response.headers.get("WWW-Authenticate", "")
    assert challenge.startswith("Bearer "), challenge
    assert "resource_metadata=" in challenge, challenge
    assert "/.well-known/oauth-protected-resource" in challenge, challenge


async def test_missing_token_returns_401_with_challenge(client):
    """No credentials at all."""
    _assert_challenge(await _post_mcp(client))


async def test_garbage_token_returns_401(client):
    """A token this server never issued."""
    _assert_challenge(await _post_mcp(client, "not-a-real-token"))


async def test_expired_token_returns_401_not_400(client, auth_store):
    """An expired token must still challenge, never fall through to a 400."""
    credential_id = auth_store.put_credential(
        {
            "name": "oauth:db",
            "url": "https://odoo.example.com",
            "database": "db",
            "user": "someone",
            "api_key": "k",
            "protocol": "json2s",
        },
        uid=7,
    )
    grant_id = auth_store.create_grant(
        client_id="c1", credential_id=credential_id, scopes=["odoo:read"], resource=None
    )
    token, _ = auth_store.put_access_token(grant_id, ttl=1)
    time.sleep(1.1)

    _assert_challenge(await _post_mcp(client, token))


async def test_revoked_token_returns_401(client, auth_store):
    """Revoking a grant invalidates its tokens immediately."""
    credential_id = auth_store.put_credential(
        {
            "name": "oauth:db",
            "url": "https://odoo.example.com",
            "database": "db",
            "user": "someone",
            "api_key": "k",
            "protocol": "json2s",
        },
        uid=7,
    )
    grant_id = auth_store.create_grant(
        client_id="c1", credential_id=credential_id, scopes=["odoo:read"], resource=None
    )
    token, _ = auth_store.put_access_token(grant_id, ttl=3600)

    assert auth_store.revoke_grant(grant_id) is True
    _assert_challenge(await _post_mcp(client, token))


@pytest.mark.parametrize("path", ["/odoo/login", "/health", "/.well-known/oauth-protected-resource"])
async def test_public_paths_do_not_challenge(client, path):
    """The consent flow and discovery must stay reachable without a token."""
    response = await client.get(path)
    assert response.status_code != 401

"""Two users, two Odoo instances, one process — and no leakage between them.

This is the test the whole HTTP design exists to pass. Over stdio a single
process serves a single user, so the active Odoo profile lives in a module
global. Over HTTP that global would hand one user's credentials to another,
so the profile is resolved per request from the bearer token.

The failure this guards against is silent and severe: a tool call answering
with data from someone else's Odoo. So the assertion is not "it usually
works" but "every one of many interleaved calls used exactly the credentials
its own token was issued for".
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import patch

import pytest

from tests.conftest import PUBLIC_HOST

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

ALICE = {
    "name": "oauth:alpha",
    "url": "https://alpha.odoo.example",
    "database": "alpha_db",
    "user": "alice@example.com",
    "api_key": "alice-key",
    "protocol": "json2s",
    "verify": True,
}

BOB = {
    "name": "oauth:beta",
    "url": "https://beta.odoo.example",
    "database": "beta_db",
    "user": "bob@example.com",
    "api_key": "bob-key",
    "protocol": "json2s",
    "verify": True,
}


def _reveal(value: Any) -> str:
    """Unwrap a SecretStr the way the real Odoo client does."""
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value or "")


class RecordingClient:
    """Stand-in Odoo client that echoes the credentials it was built with."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.last_warning = None

    def execute_kw(self, model, method, args, kwargs):
        return 1

    def search_read(self, model, domain, fields, limit, offset, order):
        # A real RPC takes time; sleeping widens the window in which a
        # context leak between concurrent requests would show up.
        time.sleep(0.05)
        return [
            {
                "id": 1,
                "url": self.kwargs.get("url"),
                "database": self.kwargs.get("database"),
                "user": self.kwargs.get("user"),
                # Credentials arrive as SecretStr, which the real client
                # unwraps; do the same so the value can be asserted on.
                "api_key": _reveal(self.kwargs.get("api_key")),
            }
        ]


def _issue_token(store, profile: dict[str, Any], uid: int) -> str:
    """Create a grant for a profile and return a usable bearer token."""
    credential_id = store.put_credential(profile, uid)
    grant_id = store.create_grant(
        client_id="test-client",
        credential_id=credential_id,
        scopes=["odoo:read", "odoo:write"],
        resource=f"https://{PUBLIC_HOST}/mcp",
    )
    token, _ = store.put_access_token(grant_id, ttl=3600)
    return token


async def _call_search_read(client, token: str, call_id: int) -> dict[str, Any]:
    """Run one authenticated search_read and return the parsed payload."""
    headers = dict(MCP_HEADERS, Authorization=f"Bearer {token}")
    response = await client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": call_id,
            "method": "tools/call",
            "params": {
                "name": "search_read",
                "arguments": {"model": "res.partner", "fields": "id"},
            },
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    return json.loads(result["content"][0]["text"])


@pytest.fixture
def recording_create_client():
    """Replace the Odoo client factory with the recording stand-in."""
    with patch("odoo_mcp_multi.operations.create_client", side_effect=RecordingClient) as mock:
        yield mock


async def test_each_token_uses_only_its_own_credentials(client, auth_store, recording_create_client):
    """Interleaved calls from two tokens never cross credentials."""
    alice_token = _issue_token(auth_store, ALICE, uid=2)
    bob_token = _issue_token(auth_store, BOB, uid=3)

    async def one(index: int) -> tuple[str, dict[str, Any]]:
        who = "alice" if index % 2 == 0 else "bob"
        token = alice_token if who == "alice" else bob_token
        return who, await _call_search_read(client, token, index)

    results = await asyncio.gather(*(one(i) for i in range(20)))

    assert len(results) == 20
    for who, payload in results:
        expected = ALICE if who == "alice" else BOB
        record = payload["records"][0]
        assert record["url"] == expected["url"], f"{who} got data from {record['url']}"
        assert record["database"] == expected["database"]
        assert record["user"] == expected["user"]

    from odoo_mcp_multi import operations

    assert operations._fallback_profile is None, "HTTP mode must never set the stdio fallback"


async def test_secrets_reach_the_client_intact(client, auth_store, recording_create_client):
    """The stored API key is decrypted correctly on the way to Odoo."""
    token = _issue_token(auth_store, ALICE, uid=2)
    payload = await _call_search_read(client, token, 1)
    assert payload["records"][0]["api_key"] == "alice-key"


async def test_host_profiles_are_not_listed_over_http(client, auth_store, recording_create_client):
    """`list_available_profiles` must not disclose the operator's profiles."""
    token = _issue_token(auth_store, ALICE, uid=2)
    headers = dict(MCP_HEADERS, Authorization=f"Bearer {token}")

    response = await client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_available_profiles", "arguments": {}},
        },
    )
    assert response.status_code == 200, response.text
    payload = json.loads(response.json()["result"]["content"][0]["text"])
    assert payload == []


async def test_a_named_profile_cannot_escape_the_authorized_connection(client, auth_store, recording_create_client):
    """Asking for another profile by name is refused, not silently honoured."""
    token = _issue_token(auth_store, ALICE, uid=2)
    headers = dict(MCP_HEADERS, Authorization=f"Bearer {token}")

    response = await client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_read",
                "arguments": {"model": "res.partner", "fields": "id", "profile": "prod"},
            },
        },
    )
    assert response.status_code == 200, response.text
    payload = json.loads(response.json()["result"]["content"][0]["text"])
    assert payload["success"] is False
    assert "not available over HTTP" in payload["error"]


async def test_credentials_entered_on_the_form_reach_odoo(client, recording_create_client):
    """The whole chain: consent form → token → tool call → Odoo client.

    Ties the HTTP surface to the RPC layer end to end, so a credential lost
    anywhere in between — serialization, encryption, context propagation —
    fails here rather than in production.
    """
    from tests.test_http_oauth_flow import full_flow

    with patch(
        "odoo_mcp_multi.http.consent.op_validate_credentials",
        return_value={
            "success": True,
            "uid": 11,
            "login": "typed@example.com",
            "server_version": "19.0",
            "protocol": "json2s",
        },
    ):
        _, tokens, _ = await full_flow(client)

    payload = await _call_search_read(client, tokens["access_token"], 1)
    record = payload["records"][0]

    # These are the values GOOD_LOGIN submits on the consent form.
    assert record["url"] == "https://odoo.example.com"
    assert record["database"] == "prod"
    assert record["user"] == "someone@example.com"
    assert record["api_key"] == "an-api-key", "the secret must survive the round trip"


async def test_stdio_mode_is_untouched():
    """Without a request context, resolution still goes through profiles.json."""
    from unittest.mock import MagicMock

    from odoo_mcp_multi import operations

    sentinel = MagicMock(name="default-profile")
    with patch("odoo_mcp_multi.operations.resolve_profile", return_value=sentinel) as resolver:
        assert operations.resolve_active_profile(None) is sentinel
    resolver.assert_called_once()

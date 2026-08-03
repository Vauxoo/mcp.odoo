"""Credential validation on the consent form, with Odoo mocked at the client.

These exercise the real operations layer — only
:func:`odoo_mcp_multi.client.create_client` is replaced — so the API-key probe
and protocol resolution are genuinely under test rather than stubbed out.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from odoo_mcp_multi.operations import op_validate_credentials
from tests.test_http_oauth_flow import GOOD_LOGIN, authorize, pkce, register


@pytest.fixture
def odoo_client():
    """A stand-in Odoo client whose behaviour each test tunes."""
    client = MagicMock(name="odoo-client")
    client.authenticate.return_value = 7
    client.protocol = "json2s"
    client.execute_kw.return_value = [{"id": 7, "login": "someone@example.com"}]
    with patch("odoo_mcp_multi.operations.create_client", return_value=client):
        with patch(
            "odoo_mcp_multi.operations.get_server_version",
            return_value={"server_version": "19.0"},
        ):
            yield client


# -- op_validate_credentials ------------------------------------------------


def test_password_login_reports_the_identity(odoo_client):
    result = op_validate_credentials(url="https://odoo.example.com", database="db", user="someone", password="pw")
    assert result["success"] is True
    assert result["uid"] == 7
    assert result["server_version"] == "19.0"
    odoo_client.authenticate.assert_called_once()


def test_api_key_login_is_probed_for_real(odoo_client):
    """Json2Client.authenticate() is a no-op, so a bad key must be caught here."""
    result = op_validate_credentials(url="https://odoo.example.com", database="db", user="someone", api_key="key")
    assert result["success"] is True
    assert result["login"] == "someone@example.com"
    odoo_client.execute_kw.assert_called_once()
    model, method, *_ = odoo_client.execute_kw.call_args[0]
    assert (model, method) == ("res.users", "search_read")


def test_a_rejected_api_key_fails_validation(odoo_client):
    odoo_client.execute_kw.side_effect = RuntimeError("401 Unauthorized")
    result = op_validate_credentials(url="https://odoo.example.com", database="db", user="someone", api_key="bad")
    assert result["success"] is False
    assert "API key rejected" in result["error"]


def test_a_rejected_password_fails_validation(odoo_client):
    odoo_client.authenticate.side_effect = RuntimeError("Access denied")
    result = op_validate_credentials(url="https://odoo.example.com", database="db", user="someone", password="wrong")
    assert result["success"] is False
    assert "Access denied" in result["error"]


def test_the_resolved_protocol_is_reported(odoo_client):
    """The concrete protocol is what gets persisted, never 'auto'."""
    result = op_validate_credentials(
        url="https://odoo.example.com", database="db", user="someone", api_key="key", protocol="auto"
    )
    assert result["protocol"] == "json2s"


# -- the consent form -------------------------------------------------------


async def test_successful_consent_persists_a_concrete_protocol(client, auth_store, odoo_client):
    """No tool call should ever pay for protocol auto-detection."""
    registration = await register(client)
    _, challenge = pkce()
    txn = await authorize(client, registration["client_id"], challenge)

    response = await client.post("/odoo/login", data=dict(GOOD_LOGIN, txn=txn, protocol="auto"))
    assert response.status_code == 302, response.text

    with auth_store._connect() as conn:
        rows = conn.execute("SELECT protocol, credential_id FROM odoo_credentials").fetchall()
    assert [row["protocol"] for row in rows] == ["json2s"]

    stored = auth_store.get_credential(rows[0]["credential_id"])
    assert stored["protocol"] == "json2s"
    assert stored["api_key"] == GOOD_LOGIN["secret"]


async def test_missing_fields_do_not_reach_odoo(client, odoo_client):
    registration = await register(client)
    _, challenge = pkce()
    txn = await authorize(client, registration["client_id"], challenge)

    response = await client.post("/odoo/login", data={"txn": txn, "odoo_url": "https://x.example"})
    assert response.status_code == 200
    assert "Every field is required" in response.text
    odoo_client.authenticate.assert_not_called()


async def test_disallowed_odoo_host_is_refused(http_config, odoo_client, tmp_path):
    """The allow-list is what stops the consent form being an SSRF pivot."""
    import httpx

    from odoo_mcp_multi.http.app import build_http_app
    from tests.conftest import PUBLIC_HOST, _Lifespan

    http_config.allowed_odoo_hosts = ("odoo.mycompany.com",)
    app = build_http_app(http_config)

    async with _Lifespan(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=f"https://{PUBLIC_HOST}",
            follow_redirects=False,
        ) as scoped:
            registration = await register(scoped)
            _, challenge = pkce()
            txn = await authorize(scoped, registration["client_id"], challenge)

            response = await scoped.post(
                "/odoo/login",
                data=dict(GOOD_LOGIN, txn=txn, odoo_url="http://10.0.0.15:8069"),
            )

    assert response.status_code == 200
    assert "not allowed to connect to that host" in response.text
    odoo_client.authenticate.assert_not_called()

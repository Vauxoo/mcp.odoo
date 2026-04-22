"""T19–T21: Integration tests for Json2Client against a live Odoo 19 instance.

These tests require ODOO19_URL and ODOO19_KEY to be set in the environment
(or in tests/integration/.env.local.test). They are skipped automatically
in CI unless those variables are provided.

Run locally:
    pytest tests/integration/test_json2_real.py -v -m integration
"""

from __future__ import annotations

import pytest

from .conftest import ODOO19_URL, requires_odoo19

# ---------------------------------------------------------------------------
# T19 — search_read
# ---------------------------------------------------------------------------


@requires_odoo19
@pytest.mark.integration
def test_t19_search_read_returns_partners(odoo19_client):
    """T19: Json2Client.search_read returns a list of partner dicts from Odoo 19."""
    result = odoo19_client.execute_kw(
        "res.partner",
        "search_read",
        args=[[]],
        kwargs={"fields": ["id", "name"], "limit": 5},
    )
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert len(result) > 0, "Expected at least one partner"
    assert "id" in result[0]
    assert "name" in result[0]


# ---------------------------------------------------------------------------
# T20 — create + write + unlink (full CRUD cycle)
# ---------------------------------------------------------------------------


@requires_odoo19
@pytest.mark.integration
def test_t20_create_write_unlink_cycle(odoo19_client):
    """T20: Full CRUD cycle via Json2Client on Odoo 19 without leaving test data."""
    # Create
    partner_id = odoo19_client.execute_kw(
        "res.partner",
        "create",
        args=[[{"name": "odoo-mcp-test-T20", "is_company": False}]],
        kwargs={},
    )
    if isinstance(partner_id, list):
        partner_id = partner_id[0]
    assert isinstance(partner_id, int) and partner_id > 0, "create() must return a positive int id"

    try:
        # Write
        odoo19_client.execute_kw(
            "res.partner",
            "write",
            args=[[partner_id], {"name": "odoo-mcp-test-T20-updated"}],
            kwargs={},
        )

        # Read back to verify write
        records = odoo19_client.execute_kw(
            "res.partner",
            "read",
            args=[[partner_id], ["name"]],
            kwargs={},
        )
        assert records[0]["name"] == "odoo-mcp-test-T20-updated"

    finally:
        # Always clean up — unlink even if assertions above fail
        odoo19_client.execute_kw(
            "res.partner",
            "unlink",
            args=[[partner_id]],
            kwargs={},
        )


# ---------------------------------------------------------------------------
# T21 — detect_protocol() against real Odoo 19
# ---------------------------------------------------------------------------


@requires_odoo19
@pytest.mark.integration
def test_t21_detect_protocol_returns_json2s():
    """T21: detect_protocol() returns Protocol.JSON2S when pointed at Odoo 19."""
    from odoo_mcp_multi.utils import Protocol, detect_protocol

    result = detect_protocol(ODOO19_URL)
    assert result == Protocol.JSON2S, f"Expected Protocol.JSON2S for Odoo 19, got {result!r}"

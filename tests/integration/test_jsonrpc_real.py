"""T22–T23: Integration tests for JsonRpcClient against a live Odoo 18 instance.

Run locally:
    pytest tests/integration/test_jsonrpc_real.py -v -m integration
"""
from __future__ import annotations

import pytest

from .conftest import ODOO18_URL, requires_odoo18


# ---------------------------------------------------------------------------
# T22 — detect_protocol() against real Odoo 18
# ---------------------------------------------------------------------------


@requires_odoo18
@pytest.mark.integration
def test_t22_detect_protocol_returns_jsonrpcs():
    """T22: detect_protocol() returns Protocol.JSONRPCS when pointed at Odoo 18."""
    from odoo_mcp_multi.utils import Protocol, detect_protocol

    result = detect_protocol(ODOO18_URL)
    assert result == Protocol.JSONRPCS, (
        f"Expected Protocol.JSONRPCS for Odoo 18, got {result!r}"
    )


# ---------------------------------------------------------------------------
# T23 — search_read via JsonRpcClient on Odoo 18
# ---------------------------------------------------------------------------


@requires_odoo18
@pytest.mark.integration
def test_t23_search_read_returns_partners(odoo18_client):
    """T23: JsonRpcClient.search_read returns partner dicts from Odoo 18."""
    result = odoo18_client.execute_kw(
        "res.partner",
        "search_read",
        [[]], {"fields": ["id", "name"], "limit": 3},
    )
    assert isinstance(result, list)
    assert len(result) > 0
    assert "id" in result[0]


@requires_odoo18
@pytest.mark.integration
def test_t23b_create_write_unlink_odoo18(odoo18_client):
    """T23b: Full CRUD via JsonRpcClient on Odoo 18 — no test data left behind."""
    pid = odoo18_client.execute_kw(
        "res.partner",
        "create",
        [{"name": "odoo-mcp-test-T23b"}],
        {},
    )
    assert isinstance(pid, int) and pid > 0
    try:
        odoo18_client.execute_kw(
            "res.partner",
            "write",
            [[pid], {"name": "odoo-mcp-test-T23b-updated"}],
            {},
        )
    finally:
        odoo18_client.execute_kw("res.partner", "unlink", [[pid]], {})

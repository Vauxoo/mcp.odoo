"""T24–T25: Integration tests for XmlRpcClient (Odoo 17) and AUTO detection.

Run locally:
    pytest tests/integration/test_xmlrpc_real.py -v -m integration
"""

from __future__ import annotations

import pytest

from .conftest import (
    ODOO17_DB,
    ODOO17_PASS,
    ODOO17_URL,
    ODOO17_USER,
    ODOO18_DB,
    ODOO18_PASS,
    ODOO18_URL,
    ODOO18_USER,
    ODOO19_DB,
    ODOO19_KEY,
    ODOO19_URL,
    requires_odoo17,
    requires_odoo18,
    requires_odoo19,
)

# ---------------------------------------------------------------------------
# T24 — XmlRpcClient smoke test on Odoo 17
# ---------------------------------------------------------------------------


@requires_odoo17
@pytest.mark.integration
def test_t24_xmlrpc_search_read_real(odoo17_client):
    """T24: XmlRpcClient.search_read returns partner dicts from Odoo 17."""
    result = odoo17_client.execute_kw(
        "res.partner",
        "search_read",
        [[]],
        {"fields": ["id", "name"], "limit": 3},
    )
    assert isinstance(result, list)
    assert len(result) > 0
    assert "id" in result[0]


# ---------------------------------------------------------------------------
# T25 — create_client(AUTO) selects correct client per Odoo version
# ---------------------------------------------------------------------------


@requires_odoo19
@requires_odoo18
@requires_odoo17
@pytest.mark.integration
def test_t25_create_client_auto_detects_each_version():
    """T25: create_client with protocol=auto picks the right client class per server.

    This validates the entire detection + factory pipeline end-to-end:
      Odoo 19 → /web/version JSON  → Json2Client
      Odoo 18 → /web/jsonrpc probe → JsonRpcClient
      Odoo 17 → /web/jsonrpc probe → JsonRpcClient (or XmlRpcClient)
    """
    from odoo_mcp_multi.utils import Json2Client, JsonRpcClient, create_client

    c19 = create_client(ODOO19_URL, ODOO19_DB, api_key=ODOO19_KEY)
    assert isinstance(c19, Json2Client), f"Odoo 19 should use Json2Client, got {type(c19)}"

    c18 = create_client(ODOO18_URL, ODOO18_DB, user=ODOO18_USER, password=ODOO18_PASS)
    assert isinstance(c18, JsonRpcClient), f"Odoo 18 should use JsonRpcClient, got {type(c18)}"

    c17 = create_client(ODOO17_URL, ODOO17_DB, user=ODOO17_USER, password=ODOO17_PASS)
    # Odoo 17 can use JsonRpc or XmlRpc depending on probe — both are acceptable
    assert isinstance(c17, JsonRpcClient), f"Odoo 17 should use JsonRpcClient, got {type(c17)}"

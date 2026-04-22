"""Integration test fixtures for odoo-mcp against live Odoo 17 / 18 / 19.

Tests in this directory are skipped automatically when the required environment
variables are not set, so the regular CI pipeline keeps running with mocks only.

Usage (local):
    cp tests/integration/.env.local.test.example tests/integration/.env.local.test
    # Edit with real values (Odoo must be running)
    pytest tests/integration/ -v -m integration

Environment variables (all optional — tests skip if missing):
    ODOO19_URL   http://localhost:8069
    ODOO19_DB    odoo19_test
    ODOO19_KEY   <API key generated from Odoo 19 Settings → Users → API Keys>
    ODOO18_URL   http://localhost:8079
    ODOO18_DB    odoo18_test
    ODOO18_USER  admin
    ODOO18_PASS  admin
    ODOO17_URL   http://localhost:8089
    ODOO17_DB    odoo17_test
    ODOO17_USER  admin
    ODOO17_PASS  admin
"""
from __future__ import annotations

import os

import pytest

# Load .env.local.test if present — never overrides real env vars
_env_file = os.path.join(os.path.dirname(__file__), ".env.local.test")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# ---------------------------------------------------------------------------
# Coordinate values (read once at module load)
# ---------------------------------------------------------------------------

ODOO19_URL = os.environ.get("ODOO19_URL", "")
ODOO19_DB = os.environ.get("ODOO19_DB", "odoo19_test")
ODOO19_KEY = os.environ.get("ODOO19_KEY", "")

ODOO18_URL = os.environ.get("ODOO18_URL", "")
ODOO18_DB = os.environ.get("ODOO18_DB", "odoo18_test")
ODOO18_USER = os.environ.get("ODOO18_USER", "admin")
ODOO18_PASS = os.environ.get("ODOO18_PASS", "")

ODOO17_URL = os.environ.get("ODOO17_URL", "")
ODOO17_DB = os.environ.get("ODOO17_DB", "odoo17_test")
ODOO17_USER = os.environ.get("ODOO17_USER", "admin")
ODOO17_PASS = os.environ.get("ODOO17_PASS", "")

# ---------------------------------------------------------------------------
# Skip markers — attach to each test that needs a live instance
# ---------------------------------------------------------------------------

requires_odoo19 = pytest.mark.skipif(
    not (ODOO19_URL and ODOO19_KEY),
    reason="Odoo 19 not configured: set ODOO19_URL and ODOO19_KEY",
)
requires_odoo18 = pytest.mark.skipif(
    not (ODOO18_URL and ODOO18_PASS),
    reason="Odoo 18 not configured: set ODOO18_URL and ODOO18_PASS",
)
requires_odoo17 = pytest.mark.skipif(
    not (ODOO17_URL and ODOO17_PASS),
    reason="Odoo 17 not configured: set ODOO17_URL and ODOO17_PASS",
)


# ---------------------------------------------------------------------------
# Session-scoped client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def odoo19_client():
    """Authenticated Json2Client against the live Odoo 19 instance."""
    from odoo_mcp_multi.utils import Json2Client

    return Json2Client(url=ODOO19_URL, database=ODOO19_DB, api_key=ODOO19_KEY)


@pytest.fixture(scope="session")
def odoo18_client():
    """Authenticated JsonRpcClient against the live Odoo 18 instance."""
    from odoo_mcp_multi.utils import JsonRpcClient

    c = JsonRpcClient(ODOO18_URL, ODOO18_DB, ODOO18_USER, ODOO18_PASS)
    c.authenticate()
    return c


@pytest.fixture(scope="session")
def odoo17_client():
    """Authenticated XmlRpcClient against the live Odoo 17 instance."""
    from odoo_mcp_multi.utils import XmlRpcClient

    c = XmlRpcClient(ODOO17_URL, ODOO17_DB, ODOO17_USER, ODOO17_PASS)
    c.authenticate()
    return c

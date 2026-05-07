"""TDD tests for the Odoo 19+ JSON-2 API client (Json2Client).

All tests in this file MUST fail before Json2Client is implemented.
Run: pytest tests/test_json2_client.py -v
"""

from __future__ import annotations

import json

import pytest
from pydantic import SecretStr

from odoo_mcp_multi.utils import (
    Json2Client,
    OdooAuthenticationError,
    OdooExecutionError,
    Protocol,
    create_client,
    detect_protocol,
    get_server_version,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_URL = "https://odoo19.example.com"
API_KEY = "6578616d706c65206a736f6e20617069206b6579"
DATABASE = "mycompany"


@pytest.fixture
def client():
    """Minimal Json2Client instance for unit tests."""
    return Json2Client(url=BASE_URL, database=DATABASE, api_key=API_KEY)


# ---------------------------------------------------------------------------
# T1 — Constructor
# ---------------------------------------------------------------------------


def test_json2_client_init_with_api_key():
    """T1: Json2Client accepts api_key, stores it as SecretStr."""
    c = Json2Client(url=BASE_URL, database=DATABASE, api_key=API_KEY)
    assert c._api_key == API_KEY or (
        hasattr(c._api_key, "get_secret_value") and c._api_key.get_secret_value() == API_KEY
    )
    assert c.url == BASE_URL
    assert c.database == DATABASE


def test_json2_client_accepts_secret_str():
    """T1b: Json2Client also accepts SecretStr directly."""
    c = Json2Client(url=BASE_URL, database=DATABASE, api_key=SecretStr(API_KEY))
    assert c._api_key == API_KEY or (
        hasattr(c._api_key, "get_secret_value") and c._api_key.get_secret_value() == API_KEY
    )


# ---------------------------------------------------------------------------
# T2 — authenticate() — no UID in JSON-2
# ---------------------------------------------------------------------------


def test_json2_client_authenticate_returns_none(client):
    """T2: authenticate() returns None — JSON-2 has no UID concept."""
    result = client.authenticate()
    assert result is None


# ---------------------------------------------------------------------------
# T3 — execute_kw() — correct URL
# ---------------------------------------------------------------------------


def test_json2_client_execute_kw_correct_url(httpx_mock, client):
    """T3: execute_kw() sends POST to /json/2/<model>/<method>."""
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/json/2/res.partner/search_read",
        json=[{"id": 1, "name": "Test Partner"}],
    )
    result = client.execute_kw("res.partner", "search_read", args=[[]], kwargs={"fields": ["name"]})
    assert result == [{"id": 1, "name": "Test Partner"}]


# ---------------------------------------------------------------------------
# T4 — Bearer header
# ---------------------------------------------------------------------------


def test_json2_client_sends_bearer_header(httpx_mock, client):
    """T4: Authorization header is 'bearer <api_key>' (lowercase 'bearer')."""
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/json/2/res.partner/search_read",
        json=[],
    )
    client.execute_kw("res.partner", "search_read", args=[[]], kwargs={})
    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == f"bearer {API_KEY}"


# ---------------------------------------------------------------------------
# T5 — X-Odoo-Database header
# ---------------------------------------------------------------------------


def test_json2_client_sends_database_header(httpx_mock, client):
    """T5: X-Odoo-Database header is set to the configured database name."""
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/json/2/res.partner/search_read",
        json=[],
    )
    client.execute_kw("res.partner", "search_read", args=[[]], kwargs={})
    request = httpx_mock.get_requests()[0]
    assert request.headers["X-Odoo-Database"] == DATABASE


# ---------------------------------------------------------------------------
# T6 — HTTP 401 → OdooAuthenticationError
# ---------------------------------------------------------------------------


def test_json2_client_401_raises_auth_error(httpx_mock, client):
    """T6: HTTP 401 from server raises OdooAuthenticationError."""
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/json/2/res.partner/search_read",
        status_code=401,
        json={"name": "werkzeug.exceptions.Unauthorized", "message": "Invalid apikey"},
    )
    with pytest.raises(OdooAuthenticationError, match="Invalid apikey|401|Unauthorized"):
        client.execute_kw("res.partner", "search_read", args=[[]], kwargs={})


# ---------------------------------------------------------------------------
# T7 — HTTP 500 → OdooExecutionError
# ---------------------------------------------------------------------------


def test_json2_client_500_raises_execution_error(httpx_mock, client):
    """T7: HTTP 5xx from server raises OdooExecutionError."""
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/json/2/res.partner/search_read",
        status_code=500,
        json={"name": "odoo.exceptions.UserError", "message": "Something went wrong"},
    )
    with pytest.raises(OdooExecutionError, match="Something went wrong|500"):
        client.execute_kw("res.partner", "search_read", args=[[]], kwargs={})


# ---------------------------------------------------------------------------
# T8 — args → named params translation (search_read)
# ---------------------------------------------------------------------------


def test_json2_client_converts_args_to_named_params_search_read(httpx_mock, client):
    """T8: [[domain], {fields, limit}] → {domain, fields, limit} in JSON body."""
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/json/2/res.partner/search_read",
        json=[],
    )
    domain = [["is_company", "=", True]]
    client.execute_kw(
        "res.partner",
        "search_read",
        args=[domain],
        kwargs={"fields": ["name"], "limit": 10},
    )
    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    assert body["domain"] == domain
    assert body["fields"] == ["name"]
    assert body["limit"] == 10
    # ids should NOT be present for search_read (it's an @api.model method)
    assert "ids" not in body


# ---------------------------------------------------------------------------
# T9 — ids in body for instance methods (write, read)
# ---------------------------------------------------------------------------


def test_json2_client_ids_in_body_for_write(httpx_mock, client):
    """T9: For 'write', ids are extracted from args[0] and placed in body."""
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/json/2/res.partner/write",
        json=True,
    )
    ids = [1, 2, 3]
    vals = {"name": "Updated"}
    client.execute_kw("res.partner", "write", args=[ids, vals], kwargs={})

    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    assert body["ids"] == ids
    assert body["vals"] == vals


# ---------------------------------------------------------------------------
# T10 — create: no ids, vals in body
# ---------------------------------------------------------------------------


def test_json2_client_create_no_ids_in_body(httpx_mock, client):
    """T10: For 'create' (@api.model), no ids in body, vals is the first arg."""
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/json/2/res.partner/create",
        json=42,
    )
    vals = {"name": "New Partner", "is_company": True}
    result = client.execute_kw("res.partner", "create", args=[[vals]], kwargs={})

    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    assert "ids" not in body
    assert body["vals_list"] == [vals]
    assert result == 42


# ---------------------------------------------------------------------------
# T11 — detect_protocol() returns JSON2S for v>=19
# ---------------------------------------------------------------------------


def test_detect_protocol_json2s_for_v19(httpx_mock):
    """T11: detect_protocol() returns Protocol.JSON2S for Odoo 19+."""
    httpx_mock.add_response(
        url=f"{BASE_URL}/web/version",
        json={"version_info": [19, 0, 0, "final", 0, ""], "version": "19.0"},
    )
    result = detect_protocol(BASE_URL)
    assert result == Protocol.JSON2S


# ---------------------------------------------------------------------------
# T12 — create_client() returns Json2Client for JSON2S
# ---------------------------------------------------------------------------


def test_create_client_returns_json2_client():
    """T12: create_client() returns Json2Client instance when protocol=JSON2S."""
    c = create_client(
        url=BASE_URL,
        database=DATABASE,
        user="",
        password="",
        api_key=API_KEY,
        protocol=Protocol.JSON2S,
    )
    assert isinstance(c, Json2Client)


# ---------------------------------------------------------------------------
# T13 — get_server_version() fallback to /web/version
# ---------------------------------------------------------------------------


def test_get_server_version_uses_web_version_endpoint(httpx_mock):
    """T13: get_server_version() can use /web/version as primary (for v19+)."""
    httpx_mock.add_response(
        url=f"{BASE_URL}/web/version",
        json={"version_info": [19, 0, 0, "final", 0, ""], "version": "19.0"},
    )
    result = get_server_version(BASE_URL)
    assert result is not None
    version = result.get("server_version", "") or result.get("version", "")
    assert "19" in str(version)


# ---------------------------------------------------------------------------
# T14 — search_count: domain must be a named parameter
# ---------------------------------------------------------------------------


def test_json2_client_search_count_sends_domain(httpx_mock, client):
    """T14: search_count translates args[0] → body.domain (not _arg0)."""
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/json/2/res.partner/search_count",
        json=42,
    )
    domain = [["country_id.name", "=", "Mexico"]]
    result = client.execute_kw("res.partner", "search_count", args=[domain], kwargs={})

    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    assert body["domain"] == domain
    assert "_arg0" not in body
    assert result == 42


# ---------------------------------------------------------------------------
# T15 — default_get: fields_list must be a named parameter
# ---------------------------------------------------------------------------


def test_json2_client_default_get_sends_fields_list(httpx_mock, client):
    """T15: default_get translates args[0] → body.fields_list."""
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/json/2/res.partner/default_get",
        json={"name": False, "email": False},
    )
    fields_list = ["name", "email"]
    result = client.execute_kw("res.partner", "default_get", args=[fields_list], kwargs={})

    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    assert body["fields_list"] == fields_list
    assert "_arg0" not in body
    assert result == {"name": False, "email": False}


# ---------------------------------------------------------------------------
# T16 — load: fields and data must be named parameters
# ---------------------------------------------------------------------------


def test_json2_client_load_sends_fields_and_data(httpx_mock, client):
    """T16: load translates args[0] → body.fields, args[1] → body.data."""
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/json/2/res.partner/load",
        json={"ids": [1, 2], "messages": []},
    )
    fields = ["name", "email"]
    data = [["John", "john@example.com"], ["Jane", "jane@example.com"]]
    result = client.execute_kw("res.partner", "load", args=[fields, data], kwargs={})

    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    assert body["fields"] == fields
    assert body["data"] == data
    assert "_arg0" not in body
    assert "_arg1" not in body
    assert result == {"ids": [1, 2], "messages": []}

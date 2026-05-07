"""Tests for shared operations module.

Tests the pure business logic in operations.py using mocks,
ensuring both MCP and CLI get correct behavior.
"""

import json
from unittest.mock import MagicMock, patch

from odoo_mcp_multi.operations import (
    op_create,
    op_execute_kw,
    op_export_records,
    op_get_version,
    op_import_records,
    op_list_fields,
    op_list_models,
    op_list_profiles,
    op_search_read,
    op_write,
)

# ---------------------------------------------------------------------------
# op_list_profiles
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations.list_profiles")
def test_op_list_profiles(mock_list):
    mock_list.return_value = [
        {"name": "prod", "url": "https://odoo.example.com", "database": "prod", "user": "admin", "is_default": True},
    ]
    result = op_list_profiles()
    assert len(result) == 1
    assert result[0]["name"] == "prod"
    assert result[0]["is_default"] is True
    # Password should NOT be present
    assert "password" not in result[0]
    assert "user" not in result[0]


# ---------------------------------------------------------------------------
# op_search_read
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations._get_client")
def test_op_search_read_basic(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.search_read.return_value = [{"id": 1, "name": "Test"}]
    mock_client.execute_kw.return_value = 1  # search_count

    result = op_search_read(model="res.partner", domain="[]", fields="id,name", profile="test")

    assert isinstance(result, dict)
    assert len(result["records"]) == 1
    assert result["records"][0]["name"] == "Test"
    assert result["total"] == 1
    assert result["has_more"] is False
    mock_client.search_read.assert_called_once()


@patch("odoo_mcp_multi.operations._get_client")
def test_op_search_read_empty_fields(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.search_read.return_value = []
    mock_client.execute_kw.return_value = 0  # search_count

    result = op_search_read(model="res.partner", profile="test")

    assert result["records"] == []
    assert result["total"] == 0
    assert result["has_more"] is False
    mock_client.search_read.assert_called_once_with(
        model="res.partner", domain=[], fields=None, limit=100, offset=0, order=None
    )


# ---------------------------------------------------------------------------
# op_write
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations._get_client")
def test_op_write(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.write.return_value = True

    result = op_write(model="res.partner", ids="[1,2]", values='{"name": "Updated"}', profile="test")

    assert result["success"] is True
    assert result["updated_ids"] == [1, 2]
    mock_client.write.assert_called_once_with("res.partner", [1, 2], {"name": "Updated"})


def test_op_write_no_ids():
    result = op_write(model="res.partner", ids="", values='{"name": "X"}', profile="test")
    assert result["success"] is False
    assert "No record IDs" in result["error"]


def test_op_write_no_values():
    result = op_write(model="res.partner", ids="[1]", values="{}", profile="test")
    assert result["success"] is False
    assert "No values provided" in result["error"]


# ---------------------------------------------------------------------------
# op_create
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations._get_client")
def test_op_create(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.create.return_value = 42

    result = op_create(model="res.partner", values='{"name": "New Partner"}', profile="test")

    assert result["success"] is True
    assert result["id"] == 42
    mock_client.create.assert_called_once_with("res.partner", {"name": "New Partner"})


def test_op_create_no_values():
    result = op_create(model="res.partner", values="{}", profile="test")
    assert result["success"] is False
    assert "No values provided" in result["error"]


# ---------------------------------------------------------------------------
# op_export_records
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations._get_client")
def test_op_export_records(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_client.execute_kw.side_effect = [
        2,  # search_count
        [42, 43],  # search
        {"datas": [["ext_42", "Partner A"], ["ext_43", "Partner B"]]},  # export_data
    ]

    result = op_export_records(model="res.partner", domain="[]", fields="id,name", profile="test")

    assert result["total"] == 2
    assert len(result["records"]) == 2
    assert result["records"][0] == {"id": "ext_42", "name": "Partner A"}
    assert result["records"][1] == {"id": "ext_43", "name": "Partner B"}
    assert result["has_more"] is False


@patch("odoo_mcp_multi.operations._get_client")
def test_op_export_records_empty(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = [
        0,  # search_count
        [],  # search returns empty
    ]

    result = op_export_records(model="res.partner", profile="test")
    assert result["records"] == []
    assert result["total"] == 0
    assert result["has_more"] is False


@patch("odoo_mcp_multi.operations._get_client")
def test_op_export_records_search_error(mock_get_client):
    """Search-phase failure returns a verbose error dict."""
    mock_get_client.side_effect = RuntimeError("Connection refused")

    result = op_export_records(model="res.partner", profile="test")
    assert result["success"] is False
    assert "failed during search" in result["error"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_export_records_export_data_error(mock_get_client):
    """export_data failure returns an error dict with ids_found context."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = [
        5,  # search_count
        [1, 2],  # search
        RuntimeError("Timeout"),  # export_data
    ]

    result = op_export_records(model="res.partner", fields="id,name", profile="test")
    assert result["success"] is False
    assert "failed during export_data" in result["error"]
    assert result["ids_found"] == 2
    assert result["total"] == 5


@patch("odoo_mcp_multi.operations._get_client")
def test_op_export_records_no_datas_key(mock_get_client):
    """export_data returning None or missing 'datas' yields empty records."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = [
        1,  # search_count
        [42],  # search
        None,  # export_data returns None
    ]

    result = op_export_records(model="res.partner", fields="id", profile="test")
    assert result["records"] == []
    assert result["total"] == 1


# ---------------------------------------------------------------------------
# op_import_records
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations._get_client")
def test_op_import_records_success(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.return_value = {"ids": [44], "messages": []}

    rows_json = json.dumps([{"id": "test_id", "name": "New Name"}])
    result = op_import_records(model="res.partner", fields="id,name", rows=rows_json, profile="test")

    assert result["ids"] == [44]
    mock_client.execute_kw.assert_called_once_with("res.partner", "load", [["id", "name"], [["test_id", "New Name"]]])


@patch("odoo_mcp_multi.operations._get_client")
def test_op_import_records_list_rows(mock_get_client):
    """Rows as arrays (positional) are accepted and None → False coerced."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.return_value = {"ids": [45], "messages": []}

    rows_json = json.dumps([["ext_id", None]])
    result = op_import_records(model="res.partner", fields="id,name", rows=rows_json, profile="test")

    assert result["ids"] == [45]
    mock_client.execute_kw.assert_called_once_with("res.partner", "load", [["id", "name"], [["ext_id", False]]])


@patch("odoo_mcp_multi.operations._get_client")
def test_op_import_records_no_fields(mock_get_client):
    result = op_import_records(model="res.partner", fields="", rows='[{"name":"X"}]', profile="test")
    assert result["success"] is False
    assert "No fields provided" in result["error"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_import_records_no_rows(mock_get_client):
    result = op_import_records(model="res.partner", fields="id,name", rows="[]", profile="test")
    assert result["success"] is False
    assert "No rows provided" in result["error"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_import_records_invalid_row_type(mock_get_client):
    """Passing a non-dict/non-list row returns a verbose error."""
    rows_json = json.dumps(["just a string"])
    result = op_import_records(model="res.partner", fields="id", rows=rows_json, profile="test")
    assert result["success"] is False
    assert "Row formatting failed" in result["error"]
    assert "str" in result["error"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_import_records_server_error(mock_get_client):
    """Server-side failures return an error dict with context."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = RuntimeError("Connection reset")

    rows_json = json.dumps([{"id": "x1", "name": "Test"}])
    result = op_import_records(model="res.partner", fields="id,name", rows=rows_json, profile="test")

    assert result["success"] is False
    assert "Connection reset" in result["error"]
    assert result["fields"] == ["id", "name"]
    assert result["row_count"] == 1


# ---------------------------------------------------------------------------
# op_execute_kw
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations._get_client")
def test_op_execute_kw(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.return_value = True

    result = op_execute_kw(model="sale.order", method="action_confirm", args="[[42]]", kwargs="{}", profile="test")

    assert result["success"] is True
    assert result["result"] is True
    mock_client.execute_kw.assert_called_once_with("sale.order", "action_confirm", [[42]], {})


# ---------------------------------------------------------------------------
# op_get_version
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations.resolve_profile")
@patch("odoo_mcp_multi.operations.get_server_version")
def test_op_get_version(mock_get_version, mock_get_profile):
    mock_profile = MagicMock()
    mock_profile.url = "https://odoo.example.com"
    mock_get_profile.return_value = mock_profile
    mock_get_version.return_value = {"server_version": "17.0"}

    result = op_get_version(profile="test")
    assert result["server_version"] == "17.0"


@patch("odoo_mcp_multi.operations.resolve_profile")
@patch("odoo_mcp_multi.operations.get_server_version")
def test_op_get_version_error(mock_get_version, mock_get_profile):
    mock_profile = MagicMock()
    mock_profile.url = "https://odoo.example.com"
    mock_get_profile.return_value = mock_profile
    mock_get_version.return_value = None

    result = op_get_version(profile="test")
    assert result["success"] is False
    assert "Could not retrieve version" in result["error"]


# ---------------------------------------------------------------------------
# op_list_models
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_models(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.search_read.return_value = [
        {"name": "Contact", "model": "res.partner", "info": ""},
    ]

    result = op_list_models(search="partner", profile="test")
    assert result["success"] is True
    assert len(result["models"]) == 1
    assert result["models"][0]["model"] == "res.partner"


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_models_no_search(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.search_read.return_value = []

    result = op_list_models(profile="test")
    assert result["success"] is True
    assert result["models"] == []
    mock_client.search_read.assert_called_once_with(
        model="ir.model", domain=[], fields=["name", "model", "info"], limit=50, order="model"
    )


# ---------------------------------------------------------------------------
# op_list_fields
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_fields(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.return_value = {
        "name": {"string": "Name", "type": "char", "required": True, "help": ""},
    }

    result = op_list_fields(model="res.partner", profile="test")
    assert result["success"] is True
    assert "name" in result["fields"]
    assert result["fields"]["name"]["type"] == "char"

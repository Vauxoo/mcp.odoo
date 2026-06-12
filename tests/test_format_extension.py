"""Tests for --format support on list-fields, list-models, and export-records.

TDD: Tests written before implementation. Each function tests one format
variant for one operation, following the return-early pattern in
operations.py.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from odoo_mcp_multi.cli import main

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clear_metadata_cache():
    """Prevent cross-test pollution from the in-memory metadata cache."""
    from odoo_mcp_multi import operations

    operations._metadata_cache.clear()
    yield
    operations._metadata_cache.clear()


# ---------------------------------------------------------------------------
# op_list_fields with format
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_list_fields")
def test_cli_list_fields_format_table(mock_op):
    """list-fields --format table outputs a markdown table directly."""
    mock_op.return_value = {
        "data": "| field | type | required |\n| --- | --- | --- |\n| name | char | True |",
        "format": "table",
        "field_count": 1,
    }
    result = runner.invoke(main, ["list-fields", "-m", "res.partner", "-F", "table"])
    assert result.exit_code == 0
    assert "| field | type |" in result.output
    # Not wrapped in JSON
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.output)


@patch("odoo_mcp_multi.cli.op_list_fields")
def test_cli_list_fields_format_csv(mock_op):
    """list-fields --format csv outputs CSV directly."""
    mock_op.return_value = {
        "data": "field,type,required\nname,char,True",
        "format": "csv",
        "field_count": 1,
    }
    result = runner.invoke(main, ["list-fields", "-m", "res.partner", "-F", "csv"])
    assert result.exit_code == 0
    assert "field,type,required" in result.output


@patch("odoo_mcp_multi.cli.op_list_fields")
def test_cli_list_fields_format_json_default(mock_op):
    """list-fields without --format outputs JSON with fields dict."""
    mock_op.return_value = {
        "success": True,
        "fields": {"name": {"type": "char", "string": "Name"}},
    }
    result = runner.invoke(main, ["list-fields", "-m", "res.partner"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "fields" in parsed
    assert parsed["fields"]["name"]["type"] == "char"


@patch("odoo_mcp_multi.cli.op_list_fields")
def test_cli_list_fields_format_passed_to_operation(mock_op):
    """--format flag value is passed through to op_list_fields."""
    mock_op.return_value = {"data": "", "format": "compact", "field_count": 0}
    runner.invoke(main, ["list-fields", "-m", "res.partner", "-F", "compact"])
    mock_op.assert_called_once_with("res.partner", format="compact", profile=None)


# ---------------------------------------------------------------------------
# op_list_models with format
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_list_models")
def test_cli_list_models_format_table(mock_op):
    """list-models --format table outputs a markdown table directly."""
    mock_op.return_value = {
        "data": "| name | model |\n| --- | --- |\n| Contact | res.partner |",
        "format": "table",
        "model_count": 1,
    }
    result = runner.invoke(main, ["list-models", "--search", "partner", "-F", "table"])
    assert result.exit_code == 0
    assert "| Contact | res.partner |" in result.output


@patch("odoo_mcp_multi.cli.op_list_models")
def test_cli_list_models_format_csv(mock_op):
    """list-models --format csv outputs CSV directly."""
    mock_op.return_value = {
        "data": "name,model\nContact,res.partner",
        "format": "csv",
        "model_count": 1,
    }
    result = runner.invoke(main, ["list-models", "--search", "partner", "-F", "csv"])
    assert result.exit_code == 0
    assert "name,model" in result.output


@patch("odoo_mcp_multi.cli.op_list_models")
def test_cli_list_models_format_passed_to_operation(mock_op):
    """--format flag value is passed through to op_list_models."""
    mock_op.return_value = {"success": True, "models": []}
    runner.invoke(main, ["list-models", "-s", "partner", "-F", "table"])
    mock_op.assert_called_once_with("partner", "table", None)


# ---------------------------------------------------------------------------
# op_export_records with format
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_export_records")
def test_cli_export_records_format_table(mock_op):
    """export-records --format table outputs a markdown table directly."""
    mock_op.return_value = {
        "data": "| id | name |\n| --- | --- |\n| ext_1 | Alice |",
        "total": 1,
        "limit": 500,
        "has_more": False,
        "format": "table",
    }
    result = runner.invoke(main, ["export-records", "-m", "res.partner", "-F", "table"])
    assert result.exit_code == 0
    assert "| ext_1 | Alice |" in result.output


@patch("odoo_mcp_multi.cli.op_export_records")
def test_cli_export_records_format_passed_to_operation(mock_op):
    """--format flag value is passed through to op_export_records."""
    mock_op.return_value = {"records": [], "total": 0, "has_more": False}
    runner.invoke(main, ["export-records", "-m", "res.partner", "-f", "id,name", "-F", "csv"])
    mock_op.assert_called_once_with("res.partner", "[]", "id,name", 500, 0, "csv", None)


# ---------------------------------------------------------------------------
# operations.py: op_list_fields format dispatch
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_fields_format_table(mock_client):
    """op_list_fields with format=table returns flattened markdown table."""
    from odoo_mcp_multi.operations import op_list_fields

    client = MagicMock()
    client.execute_kw.return_value = {
        "name": {"type": "char", "string": "Name", "required": True, "help": "The name"},
        "active": {"type": "boolean", "string": "Active", "required": False, "help": ""},
    }
    mock_client.return_value = client

    result = op_list_fields("res.partner", format="table")
    assert result["format"] == "table"
    assert "data" in result
    assert "name" in result["data"]
    assert "active" in result["data"]
    assert "field_count" in result
    assert result["field_count"] == 2


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_fields_format_compact(mock_client):
    """op_list_fields with format=compact returns headers+rows structure."""
    from odoo_mcp_multi.operations import op_list_fields

    client = MagicMock()
    client.execute_kw.return_value = {
        "name": {"type": "char", "string": "Name", "required": True, "help": ""},
    }
    mock_client.return_value = client

    result = op_list_fields("res.partner", format="compact")
    assert result["format"] == "compact"
    assert "headers" in result
    assert "rows" in result


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_fields_format_html(mock_client):
    """op_list_fields with format=html returns an HTML table string."""
    from odoo_mcp_multi.operations import op_list_fields

    client = MagicMock()
    client.execute_kw.return_value = {
        "name": {"type": "char", "string": "Name", "required": True, "help": ""},
    }
    mock_client.return_value = client

    result = op_list_fields("res.partner", format="html")
    assert result["format"] == "html"
    assert "<table" in result["data"]
    assert "name" in result["data"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_fields_format_csv(mock_client):
    """op_list_fields with format=csv returns CSV with field info."""
    from odoo_mcp_multi.operations import op_list_fields

    client = MagicMock()
    client.execute_kw.return_value = {
        "name": {"type": "char", "string": "Name", "required": True, "help": ""},
    }
    mock_client.return_value = client

    result = op_list_fields("res.partner", format="csv")
    assert result["format"] == "csv"
    assert "name" in result["data"]
    assert "char" in result["data"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_fields_format_json_default(mock_client):
    """op_list_fields with default format returns fields dict unchanged."""
    from odoo_mcp_multi.operations import op_list_fields

    client = MagicMock()
    fields_data = {"name": {"type": "char", "string": "Name"}}
    client.execute_kw.return_value = fields_data
    mock_client.return_value = client

    result = op_list_fields("res.partner")
    assert "fields" in result
    assert result["fields"] == fields_data


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_fields_invalid_format(mock_client):
    """op_list_fields with invalid format returns error dict."""
    from odoo_mcp_multi.operations import op_list_fields

    result = op_list_fields("res.partner", format="invalid")
    assert result["success"] is False
    assert "Invalid format" in result["error"]


# ---------------------------------------------------------------------------
# operations.py: op_list_models format dispatch
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_models_format_table(mock_client):
    """op_list_models with format=table returns markdown table."""
    from odoo_mcp_multi.operations import op_list_models

    client = MagicMock()
    client.search_read.return_value = [
        {"name": "Contact", "model": "res.partner", "info": ""},
    ]
    mock_client.return_value = client

    result = op_list_models(format="table")
    assert result["format"] == "table"
    assert "data" in result
    assert "Contact" in result["data"]
    assert "model_count" in result


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_models_format_compact(mock_client):
    """op_list_models with format=compact returns headers+rows structure."""
    from odoo_mcp_multi.operations import op_list_models

    client = MagicMock()
    client.search_read.return_value = [
        {"name": "Contact", "model": "res.partner", "info": ""},
    ]
    mock_client.return_value = client

    result = op_list_models(format="compact")
    assert result["format"] == "compact"
    assert "headers" in result
    assert "rows" in result


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_models_format_html(mock_client):
    """op_list_models with format=html returns an HTML table string."""
    from odoo_mcp_multi.operations import op_list_models

    client = MagicMock()
    client.search_read.return_value = [
        {"name": "Contact", "model": "res.partner", "info": ""},
    ]
    mock_client.return_value = client

    result = op_list_models(format="html")
    assert result["format"] == "html"
    assert "<table" in result["data"]
    assert "Contact" in result["data"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_models_format_csv(mock_client):
    """op_list_models with format=csv returns CSV string."""
    from odoo_mcp_multi.operations import op_list_models

    client = MagicMock()
    client.search_read.return_value = [
        {"name": "Contact", "model": "res.partner", "info": ""},
    ]
    mock_client.return_value = client

    result = op_list_models(format="csv")
    assert result["format"] == "csv"
    assert "Contact" in result["data"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_models_format_json_default(mock_client):
    """op_list_models with default format returns models list."""
    from odoo_mcp_multi.operations import op_list_models

    client = MagicMock()
    models = [{"name": "Contact", "model": "res.partner", "info": ""}]
    client.search_read.return_value = models
    mock_client.return_value = client

    result = op_list_models()
    assert "models" in result
    assert result["models"] == models


@patch("odoo_mcp_multi.operations._get_client")
def test_op_list_models_invalid_format(mock_client):
    """op_list_models with invalid format returns error dict."""
    from odoo_mcp_multi.operations import op_list_models

    result = op_list_models(format="xml")
    assert result["success"] is False
    assert "Invalid format" in result["error"]


# ---------------------------------------------------------------------------
# operations.py: op_export_records format dispatch
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.operations._get_client")
def test_op_export_records_format_table(mock_client):
    """op_export_records with format=table returns markdown table."""
    from odoo_mcp_multi.operations import op_export_records

    client = MagicMock()
    client.execute_kw.side_effect = [
        5,  # search_count
        [1, 2],  # search
        {"datas": [["Alice"], ["Bob"]]},  # export_data
    ]
    mock_client.return_value = client

    result = op_export_records("res.partner", fields="name", format="table")
    assert result["format"] == "table"
    assert "data" in result
    assert "Alice" in result["data"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_export_records_format_compact(mock_client):
    """op_export_records with format=compact returns headers+rows."""
    from odoo_mcp_multi.operations import op_export_records

    client = MagicMock()
    client.execute_kw.side_effect = [
        2,
        [1, 2],
        {"datas": [["Alice"], ["Bob"]]},
    ]
    mock_client.return_value = client

    result = op_export_records("res.partner", fields="name", format="compact")
    assert result["format"] == "compact"
    assert "headers" in result
    assert "rows" in result


@patch("odoo_mcp_multi.operations._get_client")
def test_op_export_records_format_html(mock_client):
    """op_export_records with format=html returns an HTML table string."""
    from odoo_mcp_multi.operations import op_export_records

    client = MagicMock()
    client.execute_kw.side_effect = [
        1,
        [1],
        {"datas": [["Alice"]]},
    ]
    mock_client.return_value = client

    result = op_export_records("res.partner", fields="name", format="html")
    assert result["format"] == "html"
    assert "<table" in result["data"]
    assert "Alice" in result["data"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_export_records_format_csv(mock_client):
    """op_export_records with format=csv returns CSV string."""
    from odoo_mcp_multi.operations import op_export_records

    client = MagicMock()
    client.execute_kw.side_effect = [
        1,
        [1],
        {"datas": [["Alice"]]},
    ]
    mock_client.return_value = client

    result = op_export_records("res.partner", fields="name", format="csv")
    assert result["format"] == "csv"
    assert "Alice" in result["data"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_export_records_format_json_default(mock_client):
    """op_export_records without format returns records list."""
    from odoo_mcp_multi.operations import op_export_records

    client = MagicMock()
    client.execute_kw.side_effect = [
        1,  # search_count
        [1],  # search
        {"datas": [["Alice"]]},  # export_data
    ]
    mock_client.return_value = client

    result = op_export_records("res.partner", fields="name")
    assert "records" in result
    assert result["records"][0]["name"] == "Alice"

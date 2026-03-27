"""CLI integration tests using Click's CliRunner.

Tests each new CLI command to verify argument handling, output format,
and error behavior — ensuring CLI and MCP are functionally equivalent.
"""

import json
from unittest.mock import patch

from click.testing import CliRunner

from odoo_mcp_multi.cli import main

runner = CliRunner()


# ---------------------------------------------------------------------------
# search-read
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_search_read")
def test_cli_search_read(mock_op):
    mock_op.return_value = {"records": [{"id": 1, "name": "Test"}], "total": 1, "limit": 100, "offset": 0, "has_more": False, "next_offset": 100}

    result = runner.invoke(main, ["search-read", "--model", "res.partner", "--fields", "id,name"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert len(output["records"]) == 1
    assert output["records"][0]["name"] == "Test"
    assert output["has_more"] is False


@patch("odoo_mcp_multi.cli.op_search_read")
def test_cli_search_read_with_options(mock_op):
    mock_op.return_value = []

    result = runner.invoke(
        main,
        [
            "search-read",
            "--model",
            "res.partner",
            "--domain",
            "[('active','=',True)]",
            "--fields",
            "name",
            "--limit",
            "10",
            "--offset",
            "5",
            "--order",
            "name asc",
            "--profile",
            "prod",
        ],
    )

    assert result.exit_code == 0
    mock_op.assert_called_once_with("res.partner", "[('active','=',True)]", "name", 10, 5, "name asc", "prod")


@patch("odoo_mcp_multi.cli.op_search_read", side_effect=ValueError("No Odoo profile configured."))
def test_cli_search_read_error(mock_op):
    result = runner.invoke(main, ["search-read", "--model", "res.partner"])
    assert result.exit_code == 1
    assert "Error" in result.output


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_write")
def test_cli_write(mock_op):
    mock_op.return_value = {"success": True, "updated_ids": [1]}

    result = runner.invoke(main, ["write", "--model", "res.partner", "--ids", "1", "--values", '{"name": "Updated"}'])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["success"] is True


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_create")
def test_cli_create(mock_op):
    mock_op.return_value = {"success": True, "id": 42}

    result = runner.invoke(main, ["create", "--model", "res.partner", "--values", '{"name": "New"}'])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["id"] == 42


# ---------------------------------------------------------------------------
# export-records
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_export_records")
def test_cli_export_records(mock_op):
    mock_op.return_value = {"records": [{"id": "ext_1", "name": "A"}], "total": 1, "limit": 500, "offset": 0, "has_more": False, "next_offset": 500}

    result = runner.invoke(main, ["export-records", "--model", "res.partner", "--fields", "id,name"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert len(output["records"]) == 1


# ---------------------------------------------------------------------------
# import-records
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_import_records")
def test_cli_import_records(mock_op):
    mock_op.return_value = {"ids": [1], "messages": []}

    rows = json.dumps([{"id": "ext_1", "name": "Test"}])
    result = runner.invoke(main, ["import-records", "--model", "res.partner", "--fields", "id,name", "--rows", rows])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["ids"] == [1]


# ---------------------------------------------------------------------------
# execute-kw
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_execute_kw")
def test_cli_execute_kw(mock_op):
    mock_op.return_value = {"success": True, "result": True}

    result = runner.invoke(
        main, ["execute-kw", "--model", "sale.order", "--method", "action_confirm", "--args", "[[42]]"]
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["success"] is True


# ---------------------------------------------------------------------------
# get-version
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_get_version")
def test_cli_get_version(mock_op):
    mock_op.return_value = {"server_version": "17.0"}

    result = runner.invoke(main, ["get-version"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["server_version"] == "17.0"


@patch("odoo_mcp_multi.cli.op_get_version", side_effect=ValueError("No Odoo profile configured."))
def test_cli_get_version_error(mock_op):
    result = runner.invoke(main, ["get-version"])
    assert result.exit_code == 1
    assert "Error" in result.output


# ---------------------------------------------------------------------------
# list-models
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_list_models")
def test_cli_list_models(mock_op):
    mock_op.return_value = [{"name": "Contact", "model": "res.partner", "info": ""}]

    result = runner.invoke(main, ["list-models", "--search", "partner"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output[0]["model"] == "res.partner"


# ---------------------------------------------------------------------------
# list-fields
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_list_fields")
def test_cli_list_fields(mock_op):
    mock_op.return_value = {"name": {"string": "Name", "type": "char"}}

    result = runner.invoke(main, ["list-fields", "--model", "res.partner"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert "name" in output
    assert output["name"]["type"] == "char"


# ---------------------------------------------------------------------------
# Verify --help works for all new commands
# ---------------------------------------------------------------------------


def test_cli_help():
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    # All new commands should be listed
    for cmd in [
        "search-read",
        "write",
        "create",
        "export-records",
        "import-records",
        "execute-kw",
        "get-version",
        "list-models",
        "list-fields",
    ]:
        assert cmd in result.output, f"Command '{cmd}' not found in --help output"


def test_cli_search_read_help():
    result = runner.invoke(main, ["search-read", "--help"])
    assert result.exit_code == 0
    assert "--model" in result.output
    assert "--domain" in result.output

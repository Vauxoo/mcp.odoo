"""Tests for format-aware CLI output.

Verifies that _output() delivers exactly the format requested:
- table/csv/html → printed directly, no JSON wrapping
- compact → minimal JSON (headers + rows only)
- json / no format → full JSON envelope (backward compatible)
- errors → stderr + exit code 1
- pagination metadata → # comment header for non-JSON formats
"""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from odoo_mcp_multi.cli import _echo_pagination_header, _output, main

runner = CliRunner()


# ---------------------------------------------------------------------------
# _echo_pagination_header
# ---------------------------------------------------------------------------


def test_pagination_header_with_all_fields(capsys):
    """Header includes record counts and continuation offset."""
    data = {"total": 1500, "limit": 5, "has_more": True, "next_offset": 5}
    _echo_pagination_header(data)
    captured = capsys.readouterr()
    assert captured.out.startswith("# ")
    assert "5 of 1500" in captured.out
    assert "has_more=true" in captured.out
    assert "next_offset=5" in captured.out


def test_pagination_header_no_more_pages(capsys):
    """When has_more is False, only show counts — no continuation info."""
    data = {"total": 3, "limit": 100, "has_more": False}
    _echo_pagination_header(data)
    captured = capsys.readouterr()
    assert "has_more" not in captured.out
    assert "100 of 3" in captured.out


def test_pagination_header_empty_data(capsys):
    """No header printed when pagination metadata is absent."""
    _echo_pagination_header({})
    captured = capsys.readouterr()
    assert captured.out == ""


def test_pagination_header_no_total(capsys):
    """No header when total is missing — some responses lack pagination."""
    _echo_pagination_header({"has_more": False})
    captured = capsys.readouterr()
    assert captured.out == ""


# ---------------------------------------------------------------------------
# _output — table format: direct output, no JSON wrapping
# ---------------------------------------------------------------------------


def test_output_table_prints_directly(capsys):
    """Table format bypasses json.dumps and prints the markdown table raw."""
    table_str = "| id | name |\n| --- | --- |\n| 1 | Alice |"
    data = {
        "data": table_str,
        "total": 10,
        "limit": 5,
        "has_more": True,
        "next_offset": 5,
        "format": "table",
    }
    _output(data)
    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    # First line is the pagination comment header
    assert lines[0].startswith("# ")
    # Remaining lines are the raw table
    assert "| id | name |" in captured.out
    # NOT wrapped in JSON
    with pytest.raises(json.JSONDecodeError):
        json.loads(captured.out)


def test_output_table_no_pagination(capsys):
    """Table without pagination metadata still prints directly."""
    table_str = "| a |\n| --- |\n| 1 |"
    data = {"data": table_str, "format": "table"}
    _output(data)
    captured = capsys.readouterr()
    assert captured.out.strip() == table_str


# ---------------------------------------------------------------------------
# _output — csv format: direct output
# ---------------------------------------------------------------------------


def test_output_csv_prints_directly(capsys):
    """CSV format prints RFC 4180 content directly."""
    csv_str = "name,email\nAlice,alice@x.com"
    data = {
        "data": csv_str,
        "total": 1,
        "limit": 100,
        "has_more": False,
        "format": "csv",
    }
    _output(data)
    captured = capsys.readouterr()
    assert "name,email" in captured.out
    assert "Alice,alice@x.com" in captured.out


# ---------------------------------------------------------------------------
# _output — html format: direct output
# ---------------------------------------------------------------------------


def test_output_html_prints_directly(capsys):
    """HTML format prints the HTML string directly."""
    html_str = "<table><tr><td>Alice</td></tr></table>"
    data = {"data": html_str, "format": "html"}
    _output(data)
    captured = capsys.readouterr()
    assert captured.out.strip() == html_str


# ---------------------------------------------------------------------------
# _output — compact format: minimal JSON (headers + rows only)
# ---------------------------------------------------------------------------


def test_output_compact_prints_minimal_json(capsys):
    """Compact format prints only headers+rows, no envelope overhead."""
    data = {
        "headers": ["id", "name"],
        "rows": [[1, "Alice"], [2, "Bob"]],
        "total": 100,
        "limit": 2,
        "has_more": True,
        "next_offset": 2,
        "format": "compact",
    }
    _output(data)
    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    # First line is pagination header
    assert lines[0].startswith("# ")
    # JSON payload contains only headers + rows
    payload = json.loads(lines[1])
    assert payload == {"headers": ["id", "name"], "rows": [[1, "Alice"], [2, "Bob"]]}
    assert "total" not in payload
    assert "format" not in payload


# ---------------------------------------------------------------------------
# _output — json format: full envelope (backward compatible)
# ---------------------------------------------------------------------------


def test_output_json_preserves_envelope(capsys):
    """JSON format retains the full envelope for backward compatibility."""
    data = {
        "records": [{"id": 1, "name": "Alice"}],
        "total": 1,
        "limit": 100,
        "offset": 0,
        "has_more": False,
        "next_offset": 100,
        "format": "json",
    }
    _output(data)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert "records" in parsed
    assert "total" in parsed
    assert parsed["format"] == "json"


def test_output_no_format_key_defaults_to_json(capsys):
    """Results without 'format' key (write, create, etc.) output full JSON."""
    data = {"success": True, "id": 42}
    _output(data)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"success": True, "id": 42}


def test_output_non_dict_data_outputs_json(capsys):
    """Non-dict payloads (e.g. list from list_profiles) go straight to JSON."""
    data = [{"name": "prod", "url": "https://example.com"}]
    _output(data)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["name"] == "prod"


# ---------------------------------------------------------------------------
# _output — error handling
# ---------------------------------------------------------------------------


def test_output_error_goes_to_stderr(capsys):
    """Errors print to stderr and raise SystemExit(1)."""
    data = {"success": False, "error": "Model not found"}
    with pytest.raises(SystemExit):
        _output(data)
    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert "Model not found" in captured.err


def test_output_error_direct(capsys):
    """Direct _output() error test — stderr + SystemExit."""
    data = {"success": False, "error": "Connection refused"}
    with pytest.raises(SystemExit):
        _output(data)
    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert "Connection refused" in captured.err


# ---------------------------------------------------------------------------
# CLI integration: search-read with --format table
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_search_read")
def test_cli_search_read_table_no_json_wrapping(mock_op):
    """CLI search-read --format table outputs table directly, not JSON."""
    mock_op.return_value = {
        "data": "| id | name |\n| --- | --- |\n| 1 | Test |",
        "total": 1,
        "limit": 100,
        "has_more": False,
        "format": "table",
    }
    result = runner.invoke(main, ["search-read", "-m", "res.partner", "-F", "table"])
    assert result.exit_code == 0
    assert "| id | name |" in result.output
    # Should NOT be valid JSON
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.output)


@patch("odoo_mcp_multi.cli.op_search_read")
def test_cli_search_read_csv_no_json_wrapping(mock_op):
    """CLI search-read --format csv outputs CSV directly."""
    mock_op.return_value = {
        "data": "name,email\nAlice,a@x.com",
        "total": 1,
        "limit": 100,
        "has_more": False,
        "format": "csv",
    }
    result = runner.invoke(main, ["search-read", "-m", "res.partner", "-F", "csv"])
    assert result.exit_code == 0
    assert "name,email" in result.output
    assert "Alice,a@x.com" in result.output


@patch("odoo_mcp_multi.cli.op_search_read")
def test_cli_search_read_json_preserves_envelope(mock_op):
    """CLI search-read --format json (default) keeps full JSON envelope."""
    mock_op.return_value = {
        "records": [{"id": 1}],
        "total": 1,
        "limit": 100,
        "has_more": False,
        "format": "json",
    }
    result = runner.invoke(main, ["search-read", "-m", "res.partner"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "records" in parsed


@patch("odoo_mcp_multi.cli.op_search_read")
def test_cli_search_read_error_to_stderr(mock_op):
    """CLI error responses go to stderr with exit code 1."""
    mock_op.return_value = {"success": False, "error": "Model 'fake' not found"}
    result = runner.invoke(main, ["search-read", "-m", "fake"])
    assert result.exit_code == 1
    # CliRunner mixes stdout/stderr — check the output contains ERROR
    assert "ERROR:" in result.output

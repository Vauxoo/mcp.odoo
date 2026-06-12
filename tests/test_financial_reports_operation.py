"""Tests for get_financial_report operation."""

from unittest.mock import MagicMock, patch

from odoo_mcp_multi.operations import op_get_financial_report

# Standard mock objects for options and calculated report results.
MOCK_OPTIONS = {
    "report_id": 424,
    "columns": [{"name": "Balance", "column_group_key": "grp1"}],
    "column_headers": [[{"name": "As of 12/06/2026", "colspan": 1}]],
    "column_headers_render_data": {"level_colspan": [1], "level_repetitions": [1]},
}

MOCK_REPORT_INFO = {
    "lines": [
        {
            "id": "line_0",
            "name": "Assets",
            "level": 0,
            "columns": [{"name": "$100"}],
        },
        {
            "id": "line_1",
            "name": "Current Assets",
            "level": 1,
            "columns": [{"name": "$60"}],
        },
        {
            "id": "line_2",
            "name": "Cash",
            "level": 2,
            "columns": [{"name": "$40"}],
        },
        {
            "id": "line_1|total~~",
            "name": "Total Current Assets",
            "level": 1,
            "columns": [{"name": "$60"}],
        },
    ],
    "report": {
        "name": "Balance Sheet",
        "company_name": "Test Company",
    },
}


@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_json(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # Mock get_options and get_report_information RPC calls
    mock_client.execute_kw.side_effect = [MOCK_OPTIONS, MOCK_REPORT_INFO]

    result = op_get_financial_report(report_id_or_name=4, format="json", profile="test")

    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["report_info"] == MOCK_REPORT_INFO
    assert result["options"] == MOCK_OPTIONS

    # Verify both RPC calls
    assert mock_client.execute_kw.call_count == 2


@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_table(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = [MOCK_OPTIONS, MOCK_REPORT_INFO]

    result = op_get_financial_report(report_id_or_name=4, format="table", profile="test")

    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["format"] == "table"

    data = result["data"]
    assert "| Concept | Balance |" in data
    assert "| Assets | $100 |" in data
    # Level 2 Cash should have indentation space (4 spaces from level + 1 leading space)
    assert "|     Cash | $40 |" in data
    # Level 1 should have smaller indentation
    assert "|   Total Current Assets | $60 |" in data


@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_csv(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = [MOCK_OPTIONS, MOCK_REPORT_INFO]

    result = op_get_financial_report(report_id_or_name=4, format="csv", profile="test")

    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["format"] == "csv"

    data = result["data"]
    lines = data.splitlines()
    assert lines[0] == "Concept,Balance"
    assert lines[1] == "Assets,$100"
    assert lines[2] == "  Current Assets,$60"
    assert lines[3] == "    Cash,$40"


@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_html(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = [MOCK_OPTIONS, MOCK_REPORT_INFO]

    result = op_get_financial_report(report_id_or_name=4, format="html", profile="test")

    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["format"] == "html"

    html = result["data"]
    # Verify overall HTML layout and styling
    assert "<!DOCTYPE html>" in html
    assert "<title>Balance Sheet</title>" in html
    assert "Test Company" in html
    assert "class='account_report_table'" in html

    # Verify column headers row
    assert "<th colspan='1'>As of 12/06/2026</th>" in html
    assert "<th class='concept-header'>Concept</th>" in html
    assert "<th>Balance</th>" in html

    # Verify Odoo-like spacing row before level 0 rows is present in code
    assert "<tr class='empty'>" in html

    # Verify level classes and indentation style
    assert "class='line_level_0'" in html
    assert "class='line_level_1'" in html
    # Cash at level 2 should have padding corresponding to ((2 + 1) * 8) - 20 = 4px
    assert "padding-left: 4px;" in html

    # Verify total line styling
    assert "class='line_level_1 total'" in html
    assert "border-bottom: 2px double #212529" in html


@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_resolution(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = [MOCK_OPTIONS, MOCK_REPORT_INFO]

    # Mock name search in account.report
    mock_client.search_read.side_effect = [
        [{"id": 4}],  # first call to search account.report by name
    ]

    # Resolve by name string
    result = op_get_financial_report(report_id_or_name="Balance Sheet", format="json", profile="test")
    assert result["success"] is True
    mock_client.search_read.assert_called_once_with("account.report", [("name", "=", "Balance Sheet")], ["id"])

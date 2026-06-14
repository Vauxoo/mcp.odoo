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
    assert "<th colspan='1' class='concept-header'>Concept</th>" in html
    assert "<th colspan='1'>Balance</th>" in html

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


@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_xml_id(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = [MOCK_OPTIONS, MOCK_REPORT_INFO, MOCK_OPTIONS, MOCK_REPORT_INFO]

    # Mock XML ID search in ir.model.data
    # First call: res_id exists, Second call: does not exist
    mock_client.search_read.side_effect = [
        [{"res_id": 123}],
        [],
    ]

    # Case 1: XML ID exists
    result = op_get_financial_report(report_id_or_name="account.gallery_balance_sheet", format="json", profile="test")
    assert result["success"] is True

    # Case 2: XML ID does not exist (falls through to return None and fail)
    result_missing = op_get_financial_report(
        report_id_or_name="account.nonexistent_report", format="json", profile="test"
    )
    assert result_missing["success"] is False

    assert "Could not resolve financial report" in result_missing["error"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_ilike_and_missing(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = [MOCK_OPTIONS, MOCK_REPORT_INFO, MOCK_OPTIONS, MOCK_REPORT_INFO]

    # First run: exact match fails, ilike match succeeds
    mock_client.search_read.side_effect = [
        [],  # exact name fails
        [{"id": 456}],  # ilike succeeds
        [],  # exact name fails (second run)
        [],  # ilike fails (second run)
    ]

    # Case 1: resolves by ilike
    result_ilike = op_get_financial_report(report_id_or_name="balance sheet", format="json", profile="test")
    assert result_ilike["success"] is True

    # Case 2: fails to resolve
    result_missing = op_get_financial_report(report_id_or_name="Nonexistent Report", format="json", profile="test")
    assert result_missing["success"] is False
    assert "Could not resolve financial report" in result_missing["error"]


def test_op_get_financial_report_invalid_format():
    result = op_get_financial_report(report_id_or_name=4, format="pdf", profile="test")
    assert result["success"] is False
    assert "Invalid format" in result["error"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_dates_and_options(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = [
        MOCK_OPTIONS,
        MOCK_REPORT_INFO,
        MOCK_OPTIONS,
        MOCK_REPORT_INFO,
        MOCK_OPTIONS,
        MOCK_REPORT_INFO,
        MOCK_OPTIONS,
        MOCK_REPORT_INFO,
    ]

    # Test 1: filter and custom dates
    op_get_financial_report(
        report_id_or_name=4,
        date_from="2025-01-01",
        date_to="2025-12-31",
        date_filter="this_year",
        format="json",
        profile="test",
    )
    first_call_options = mock_client.execute_kw.call_args_list[0][0][2]
    assert first_call_options[1]["date"]["filter"] == "this_year"
    assert first_call_options[1]["date"]["date_from"] == "2025-01-01"
    assert first_call_options[1]["date"]["date_to"] == "2025-12-31"

    # Test 2: date_from only (triggers custom filter assignment)
    op_get_financial_report(
        report_id_or_name=4,
        date_from="2025-01-01",
        format="json",
        profile="test",
    )
    second_call_options = mock_client.execute_kw.call_args_list[2][0][2]
    assert second_call_options[1]["date"]["filter"] == "custom"
    assert second_call_options[1]["date"]["date_from"] == "2025-01-01"

    # Test 3: date_to only (triggers custom filter assignment)
    op_get_financial_report(
        report_id_or_name=4,
        date_to="2025-12-31",
        format="json",
        profile="test",
    )
    third_call_options = mock_client.execute_kw.call_args_list[4][0][2]
    assert third_call_options[1]["date"]["filter"] == "custom"
    assert third_call_options[1]["date"]["date_to"] == "2025-12-31"

    # Test 4: date_filter only (no custom date)
    op_get_financial_report(
        report_id_or_name=4,
        date_filter="today",
        format="json",
        profile="test",
    )
    fourth_call_options = mock_client.execute_kw.call_args_list[6][0][2]
    assert fourth_call_options[1]["date"]["filter"] == "today"
    assert "date_from" not in fourth_call_options[1]["date"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_rpc_exception(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = Exception("Odoo RPC Error")

    result = op_get_financial_report(report_id_or_name=4, format="json", profile="test")
    assert result["success"] is False
    assert "Failed to get financial report: Odoo RPC Error" in result["error"]


def test_format_report_html_branches_directly():
    from odoo_mcp_multi.operations import _format_financial_report, _format_report_html

    # 1. No level and level 1 (where padding calculations <= 0)
    lines_with_edge_cases = [
        {
            "id": "line_no_level",
            "name": "No Level Concept",
            "level": None,
            "columns": [],
        },
        {
            "id": "line_level_1",
            "name": "Level 1 Concept",
            "level": 1,
            "columns": [],
        },
    ]

    # No company name and fallback colspan
    options_without_colspan = {
        "columns": [],
        "column_headers": [[{"name": "Date Header"}]],  # no colspan
        "column_headers_render_data": {"level_colspan": [2]},
    }

    html = _format_report_html(
        options_without_colspan,
        lines_with_edge_cases,
        cols=[],
        report_meta={"name": "Edge Cases Report"},  # no company_name
    )

    assert "line_level_default" in html
    assert "line_level_1" in html
    assert "colspan='2'" in html
    assert "<p class='report-company'>" not in html

    # 3. Test company_ids joining in _format_report_html
    html_with_companies = _format_report_html(
        {"companies": [{"name": "Vauxoo Consultores"}, {"name": "Vauxoo"}]},
        [],
        cols=[],
        report_meta={"name": "Test Report", "company_name": "Single Company"},
        company_ids="19,1",
    )
    assert "<p class='report-company'>Vauxoo Consultores, Vauxoo</p>" in html_with_companies

    # 4. Test fallback in _format_financial_report directly
    unsupported_res = _format_financial_report({}, {"lines": []}, "unsupported_format")
    assert unsupported_res == ""


@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_company_ids(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = [MOCK_OPTIONS, MOCK_REPORT_INFO, MOCK_OPTIONS, MOCK_REPORT_INFO]

    # Test with string company IDs
    res = op_get_financial_report(report_id_or_name=4, format="json", profile="test", company_ids="19,1")
    assert res["success"] is True
    # The fourth positional argument is the kwargs dict passed to execute_kw
    args_1 = mock_client.execute_kw.call_args_list[0][0]
    assert args_1[3] == {"context": {"allowed_company_ids": [19, 1]}}

    # Test with list company IDs
    res2 = op_get_financial_report(report_id_or_name=4, format="json", profile="test", company_ids=[1, 19])
    assert res2["success"] is True
    args_2 = mock_client.execute_kw.call_args_list[2][0]
    assert args_2[3] == {"context": {"allowed_company_ids": [1, 19]}}

    # Test with invalid company IDs string
    res3 = op_get_financial_report(report_id_or_name=4, format="json", profile="test", company_ids="invalid,1")
    assert res3["success"] is False
    assert "Invalid company_ids" in res3["error"]

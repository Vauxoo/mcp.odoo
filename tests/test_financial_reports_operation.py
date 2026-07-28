"""Tests for get_financial_report operation."""

from unittest.mock import MagicMock, patch

import pytest

from odoo_mcp_multi.exceptions import OdooMethodNotFoundError
from odoo_mcp_multi.operations import _validate_server_version, op_get_financial_report

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
    assert 'class="line_level_0"' in html
    assert 'class="line_level_1"' in html
    # Cash at level 2 should have padding corresponding to ((2 + 1) * 8) - 20 = 4px
    assert "padding-left: 4px;" in html

    # Verify total line styling
    assert 'class="line_level_1 total"' in html


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
    # previous_options is now passed as a named kwarg (4th positional arg to execute_kw)
    # to ensure the JSON-2 client serializes it with the correct parameter name.
    first_call_odoo_kwargs = mock_client.execute_kw.call_args_list[0][0][3]
    assert first_call_odoo_kwargs["previous_options"]["date"]["filter"] == "this_year"
    assert first_call_odoo_kwargs["previous_options"]["date"]["date_from"] == "2025-01-01"
    assert first_call_odoo_kwargs["previous_options"]["date"]["date_to"] == "2025-12-31"

    # Test 2: date_from only (triggers custom filter assignment)
    op_get_financial_report(
        report_id_or_name=4,
        date_from="2025-01-01",
        format="json",
        profile="test",
    )
    second_call_odoo_kwargs = mock_client.execute_kw.call_args_list[2][0][3]
    assert second_call_odoo_kwargs["previous_options"]["date"]["filter"] == "custom"
    assert second_call_odoo_kwargs["previous_options"]["date"]["date_from"] == "2025-01-01"

    # Test 3: date_to only (triggers custom filter assignment)
    op_get_financial_report(
        report_id_or_name=4,
        date_to="2025-12-31",
        format="json",
        profile="test",
    )
    third_call_odoo_kwargs = mock_client.execute_kw.call_args_list[4][0][3]
    assert third_call_odoo_kwargs["previous_options"]["date"]["filter"] == "custom"
    assert third_call_odoo_kwargs["previous_options"]["date"]["date_to"] == "2025-12-31"

    # Test 4: date_filter only (no custom date)
    op_get_financial_report(
        report_id_or_name=4,
        date_filter="today",
        format="json",
        profile="test",
    )
    fourth_call_odoo_kwargs = mock_client.execute_kw.call_args_list[6][0][3]
    assert fourth_call_odoo_kwargs["previous_options"]["date"]["filter"] == "today"
    assert "date_from" not in fourth_call_odoo_kwargs["previous_options"]["date"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_rpc_exception(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = Exception("Odoo RPC Error")

    result = op_get_financial_report(report_id_or_name=4, format="json", profile="test")
    assert result["success"] is False
    assert "Failed to get financial report: Odoo RPC Error" in result["error"]


@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_unsupported_method_exception(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.execute_kw.side_effect = Exception("Object account.report has no attribute 'get_options'")

    result = op_get_financial_report(report_id_or_name=4, format="json", profile="test")
    assert result["success"] is False
    assert "is not supported on this Odoo version" in result["error"]


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
    # context is the 4th positional arg passed to execute_kw (the Odoo kwargs dict)
    odoo_kwargs_1 = mock_client.execute_kw.call_args_list[0][0][3]
    assert odoo_kwargs_1["context"] == {"allowed_company_ids": [19, 1]}

    # Test with list company IDs
    res2 = op_get_financial_report(report_id_or_name=4, format="json", profile="test", company_ids=[1, 19])
    assert res2["success"] is True
    odoo_kwargs_2 = mock_client.execute_kw.call_args_list[2][0][3]
    assert odoo_kwargs_2["context"] == {"allowed_company_ids": [1, 19]}

    # Test with invalid company IDs string
    res3 = op_get_financial_report(report_id_or_name=4, format="json", profile="test", company_ids="invalid,1")
    assert res3["success"] is False
    assert "Invalid company_ids" in res3["error"]


def test_format_report_html_autoescape_injection():
    from odoo_mcp_multi.operations import _format_report_html

    html = _format_report_html(
        options={"column_headers": [[{"name": "<script>alert(1)</script>"}]]},
        lines=[{"id": "1", "name": "<b>Inject</b>", "level": 0, "columns": []}],
        cols=[],
        report_meta={"name": "<i>XSS</i>", "company_name": "<u>Vauxoo</u>"},
    )
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;Inject&lt;/b&gt;" in html
    assert "&lt;i&gt;XSS&lt;/i&gt;" in html
    assert "&lt;u&gt;Vauxoo&lt;/u&gt;" in html
    # css_content is trusted and must NOT be escaped
    assert "body {" in html


def test_assert_no_credentials():
    from odoo_mcp_multi.operations import _assert_no_credentials

    # Valid data should not raise
    _assert_no_credentials({"name": "Report Name", "company": "Vauxoo"})

    # Dictionary keys containing secrets should raise
    import pytest

    with pytest.raises(ValueError, match="Sensitive key"):
        _assert_no_credentials({"api_key": "somekey"})

    # Nested dictionary keys containing secrets should raise
    with pytest.raises(ValueError, match="Sensitive key"):
        _assert_no_credentials({"nested": {"password": "pwd"}})

    # Nested lists containing dicts with secrets should raise
    with pytest.raises(ValueError, match="Sensitive key"):
        _assert_no_credentials([{"name": "test"}, {"secret": "secretvalue"}])

    # String values with assignments should raise
    with pytest.raises(ValueError, match="Potential assignment"):
        _assert_no_credentials("Here is api_key=secret")


def test_load_template_resource_security():
    import pytest

    from odoo_mcp_multi.operations import _load_template_resource

    # Safe loading should pass
    css = _load_template_resource("financial_report.css")
    assert "body {" in css

    # Relative paths with authorized basenames should succeed
    html = _load_template_resource("templates/financial_report.html")
    assert "report_name" in html

    # Path traversal / unknown filename should raise ValueError
    with pytest.raises(ValueError, match="Could not load resource"):
        _load_template_resource("some_other_file.txt")

    with pytest.raises(ValueError, match="Could not load resource"):
        _load_template_resource("../operations.py")

    with pytest.raises(ValueError, match="Could not load resource"):
        _load_template_resource("..\\operations.py")


@patch("odoo_mcp_multi.operations.get_server_version")
@patch("odoo_mcp_multi.operations._get_client")
def test_op_get_financial_report_version_compatibility(mock_get_client, mock_get_server_version):
    mock_client = MagicMock()
    mock_client.url = "http://real-odoo-url.com"
    mock_client.verify = True
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
        MOCK_OPTIONS,
        MOCK_REPORT_INFO,
        MOCK_OPTIONS,
        MOCK_REPORT_INFO,
    ]

    # Test Odoo 16.0 (unsupported)
    mock_get_server_version.return_value = {"server_version": "16.0"}
    res = op_get_financial_report(report_id_or_name=4, format="json", profile="test")
    assert res["success"] is False
    assert "requires Odoo 17.0+" in res["error"]

    # Test Odoo 17.0 (supported with warning)
    mock_client.last_warning = None
    mock_get_server_version.return_value = {"server_version": "17.0"}
    res2 = op_get_financial_report(report_id_or_name=4, format="json", profile="test")
    assert res2["success"] is True
    assert "Using plural Odoo 17/18 get_report_informations" in mock_client.last_warning

    # Test Odoo 18.0 (supported with warning)
    mock_client.last_warning = None
    mock_get_server_version.return_value = {"server_version": "18.0"}
    res3 = op_get_financial_report(report_id_or_name=4, format="json", profile="test")
    assert res3["success"] is True
    assert "Using plural Odoo 17/18 get_report_informations" in mock_client.last_warning

    # Test Odoo 19.0 (supported without compatibility warning)
    mock_client.last_warning = None
    mock_get_server_version.return_value = {"server_version": "19.0"}
    res4 = op_get_financial_report(report_id_or_name=4, format="json", profile="test")
    assert res4["success"] is True
    assert mock_client.last_warning is None

    # Test get_server_version returning None (continues without warning)
    mock_client.last_warning = None
    mock_get_server_version.return_value = None
    res_none = op_get_financial_report(report_id_or_name=4, format="json", profile="test")
    assert res_none["success"] is True
    assert mock_client.last_warning is None

    # Test get_server_version exception (fails gracefully with warning)
    mock_client.last_warning = None
    mock_get_server_version.side_effect = Exception("Connection refused")
    res5 = op_get_financial_report(report_id_or_name=4, format="json", profile="test")
    assert res5["success"] is True
    assert "Could not verify Odoo server version compatibility: Connection refused" in mock_client.last_warning

    # Verify correct methods are invoked according to version detection
    calls = mock_client.execute_kw.call_args_list
    assert calls[1][0][1] == "get_report_informations"  # Odoo 17.0
    assert calls[3][0][1] == "get_report_informations"  # Odoo 18.0
    assert calls[5][0][1] == "get_report_information"  # Odoo 19.0
    assert calls[7][0][1] == "get_report_information"  # None version (default)
    assert calls[9][0][1] == "get_report_information"  # Exception version (default)


@patch("odoo_mcp_multi.operations.get_server_version")
@patch("odoo_mcp_multi.operations._get_client")
def test_get_financial_report_dynamic_fallback(mock_get_client, mock_get_server_version):
    mock_client = MagicMock()
    mock_client.url = "http://real-odoo-url.com"
    mock_client.verify = True
    mock_get_client.return_value = mock_client
    mock_get_server_version.return_value = None  # Force fallback behavior

    # Mock execute_kw to fail on first call to get_report_information but succeed on get_report_informations
    def side_effect(model, method, args, kwargs=None):
        if method == "get_options":
            return MOCK_OPTIONS
        if method == "get_report_information":
            # Simulate method not existing
            raise OdooMethodNotFoundError("object has no attribute 'get_report_information'")
        if method == "get_report_informations":
            return MOCK_REPORT_INFO
        raise Exception("unexpected method")

    mock_client.execute_kw.side_effect = side_effect

    res = op_get_financial_report(report_id_or_name=4, format="json", profile="test")
    assert res["success"] is True
    assert "Switched dynamically to fallback method" in mock_client.last_warning

    # Test when both methods fail
    mock_client.execute_kw.side_effect = [
        MOCK_OPTIONS,
        OdooMethodNotFoundError("object has no attribute 'get_report_information'"),
        OdooMethodNotFoundError("object has no attribute 'get_report_informations'"),
    ]
    res2 = op_get_financial_report(report_id_or_name=4, format="json", profile="test")
    assert res2["success"] is False
    assert "Failed to get financial report" in res2["error"]


def test_load_template_resource_error_wrapping():
    from unittest.mock import patch

    import pytest

    from odoo_mcp_multi.operations import _load_template_resource

    # Verify that any generic package resource errors are caught and wrapped in ValueError
    with patch("importlib.resources.files", side_effect=Exception("Package resource error")):
        with pytest.raises(ValueError, match="Could not load resource"):
            _load_template_resource("financial_report.css")


def test_get_financial_report_inline_compat_fail():
    from unittest.mock import patch

    from odoo_mcp_multi.operations import op_get_financial_report

    with (
        patch("odoo_mcp_multi.operations._get_client"),
        patch("odoo_mcp_multi.operations._validate_server_version", return_value=("16.0", 16)),
    ):
        res = op_get_financial_report(report_id_or_name=4, format="json", profile="test")
        assert res["success"] is False
        assert "requires Odoo 17.0+" in res["error"]


def test_validate_server_version_non_mock():
    class CustomNonMockClient:
        def __init__(self):
            self.url = "http://my-odoo.local"
            self.verify = True
            self.last_warning = None

        def search_read(self, model, domain, fields):
            if model == "ir.module.module":
                return [{"latest_version": "17.0"}]
            return []

    client = CustomNonMockClient()
    with patch("odoo_mcp_multi.operations.get_server_version", return_value=None):
        version, major = _validate_server_version(client)
        assert version == "17.0"
        assert major == 17

    client2 = CustomNonMockClient()
    client2.search_read = lambda model, domain, fields: [{"latest_version": "16.0"}]
    with patch("odoo_mcp_multi.operations.get_server_version", return_value=None):
        with pytest.raises(ValueError, match="requires Odoo 17.0+"):
            _validate_server_version(client2)

    client3 = CustomNonMockClient()

    # To simulate an actual raised exception, we can define a method that raises an error
    def fail_search_read(model, domain, fields):
        raise Exception("RPC failed")

    client3.search_read = fail_search_read
    with patch("odoo_mcp_multi.operations.get_server_version", return_value=None):
        with pytest.raises(ValueError, match="Could not determine Odoo server version"):
            _validate_server_version(client3)

    client4 = CustomNonMockClient()
    client4.search_read = lambda model, domain, fields: []
    with patch("odoo_mcp_multi.operations.get_server_version", return_value=None):
        with pytest.raises(ValueError, match="Could not determine Odoo server version"):
            _validate_server_version(client4)


def test_client_version_validation_and_caching():
    from unittest.mock import patch

    from odoo_mcp_multi.client import XmlRpcClient

    client = XmlRpcClient(
        url="http://real-odoo-url.com",
        database="testdb",
        user="admin",
        password="pwd",
    )

    # 1. Success case: public version info endpoint is reachable
    with patch("odoo_mcp_multi.client.get_server_version") as mock_get_ver:
        mock_get_ver.return_value = {"server_version": "19.0"}
        ver = client.get_server_version()
        assert ver == "19.0"
        assert client._server_version == "19.0"
        # Test caching on subsequent calls
        ver_cached = client.get_server_version()
        assert ver_cached == "19.0"
        assert mock_get_ver.call_count == 1

    # Reset cache for another client
    client2 = XmlRpcClient(
        url="http://real-odoo-url.com",
        database="testdb",
        user="admin",
        password="pwd",
    )

    # 2. Fallback case: public version info fails, falls back to ir.module.module search_read via execute_kw
    with (
        patch("odoo_mcp_multi.client.get_server_version", side_effect=Exception("Connection timed out")),
        patch.object(client2, "execute_kw") as mock_exec_kw,
    ):
        mock_exec_kw.return_value = [{"latest_version": "17.0"}]
        ver = client2.get_server_version()
        assert ver == "17.0"
        assert client2._server_version == "17.0"
        mock_exec_kw.assert_called_once_with(
            "ir.module.module", "search_read", [[("name", "=", "base")], ["latest_version"]], {}
        )

    # 3. Failure case: all endpoints fail, returns 'unknown' and raises ValueError on validation
    client3 = XmlRpcClient(
        url="http://real-odoo-url.com",
        database="testdb",
        user="admin",
        password="pwd",
    )
    with (
        patch("odoo_mcp_multi.client.get_server_version", side_effect=Exception("Failed")),
        patch.object(client3, "execute_kw", side_effect=Exception("RPC failed")),
    ):
        ver = client3.get_server_version()
        assert ver == "unknown"
        with pytest.raises(ValueError, match="Could not determine Odoo server version"):
            client3.validate_version(min_version=17, feature_name="Test")

    # 4. Success validate case
    client4 = XmlRpcClient(
        url="http://real-odoo-url.com",
        database="testdb",
        user="admin",
        password="pwd",
    )
    client4._server_version = "18.0"
    major = client4.validate_version(min_version=17, feature_name="Test")
    assert major == 18

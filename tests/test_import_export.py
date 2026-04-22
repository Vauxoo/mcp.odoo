"""Tests for import/export operations.

Tests the export_records and import_records functionality through the
shared operations module, using mocks to simulate Odoo responses.
"""

import json
from unittest.mock import MagicMock, patch

from odoo_mcp_multi.operations import op_export_records, op_import_records


@patch("odoo_mcp_multi.operations._get_client")
def test_export_records(mock_get_client):
    """Test exporting data and converting the array-of-arrays to dicts."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_client.execute_kw.side_effect = [
        2,  # return value for 'search_count'
        [42, 43],  # return value for 'search'
        {  # return value for 'export_data'
            "datas": [
                ["__export__.res_partner_42_99b00db5", "Partner A"],
                ["__export__.res_partner_43_99b00db5", "Partner B"],
            ]
        },
    ]

    result = op_export_records(model="res.partner", domain="[]", fields="id,name", profile="test")

    # Verify client calls
    assert mock_client.execute_kw.call_count == 3
    mock_client.execute_kw.assert_any_call("res.partner", "search_count", [[]], {})
    mock_client.execute_kw.assert_any_call("res.partner", "search", [[]], {"limit": 500, "offset": 0})
    mock_client.execute_kw.assert_any_call("res.partner", "export_data", [[42, 43], ["id", "name"]])

    # Verify envelope structure
    assert isinstance(result, dict)
    assert result["total"] == 2
    assert result["has_more"] is False
    assert len(result["records"]) == 2
    assert result["records"][0] == {"id": "__export__.res_partner_42_99b00db5", "name": "Partner A"}
    assert result["records"][1] == {"id": "__export__.res_partner_43_99b00db5", "name": "Partner B"}


@patch("odoo_mcp_multi.operations._get_client")
def test_import_records_success(mock_get_client):
    """Test successful import via load."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_client.execute_kw.return_value = {"ids": [44], "messages": []}

    rows_json = json.dumps([{"id": "test_id", "name": "New Name"}])
    result = op_import_records(model="res.partner", fields="id,name", rows=rows_json, profile="test")

    # Verify formatting of rows passed back to execute_kw
    mock_client.execute_kw.assert_called_once_with("res.partner", "load", [["id", "name"], [["test_id", "New Name"]]])

    assert result["ids"] == [44]


@patch("odoo_mcp_multi.operations._get_client")
def test_import_records_error(mock_get_client):
    """Test import failing via load and returning messages."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_client.execute_kw.return_value = {
        "ids": False,
        "messages": [
            {
                "message": "No matching record found for external id 'test_id' in field 'Country'",
                "field": "country_id/id",
                "record": 0,
            }
        ],
    }

    rows_json = json.dumps([{"id": "part_1", "name": "Test", "country_id/id": "test_id"}])
    result = op_import_records(model="res.partner", fields="id,name,country_id/id", rows=rows_json, profile="test")

    assert result["ids"] is False
    assert len(result["messages"]) == 1
    assert "No matching record" in result["messages"][0]["message"]

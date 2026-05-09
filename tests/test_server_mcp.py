"""Tests for the FastMCP server layer.

Validates that MCP tools are correctly registered, that call_tool()
delegates to the operations module, and that responses are valid JSON.
Uses the FastMCP in-process testing pattern (no subprocess, no ports).
"""

import json
from unittest.mock import patch

import pytest

from odoo_mcp_multi.server import mcp


def _text(call_result: tuple) -> str:
    """Extract the raw text from mcp.call_tool() return value.

    mcp 1.x call_tool() returns ``(list[TextContent], metadata_dict)``.
    """
    content_list, _meta = call_result
    return content_list[0].text


def _json_data(call_result: tuple):
    """Parse JSON from the first TextContent block."""
    return json.loads(_text(call_result))


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = sorted(
    [
        "list_available_profiles",
        "search_read",
        "write",
        "unlink",
        "create",
        "export_records",
        "import_records",
        "execute_kw",
        "list_models",
        "list_fields",
        "get_version",
    ]
)


@pytest.mark.asyncio
async def test_tool_count():
    """The server must expose exactly 11 tools."""
    tools = await mcp.list_tools()
    assert len(tools) == 11


@pytest.mark.asyncio
async def test_tool_names():
    """Every expected tool name must be registered."""
    tools = await mcp.list_tools()
    registered = sorted(t.name for t in tools)
    assert registered == EXPECTED_TOOLS


# ---------------------------------------------------------------------------
# call_tool → operations pass-through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_list_profiles")
async def test_list_available_profiles(mock_op):
    mock_op.return_value = [{"name": "prod", "url": "https://odoo.example.com"}]
    result = await mcp.call_tool("list_available_profiles", {})
    data = _json_data(result)
    assert data[0]["name"] == "prod"
    mock_op.assert_called_once()


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_search_read")
async def test_search_read_defaults(mock_op):
    """search_read with only model= uses correct defaults for all other args."""
    mock_op.return_value = {"records": [], "total": 0, "has_more": False}
    result = await mcp.call_tool("search_read", {"model": "res.partner"})
    data = _json_data(result)
    assert data["records"] == []
    mock_op.assert_called_once_with("res.partner", "[]", "", 100, 0, "", "json", None)


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_search_read")
async def test_search_read_with_profile(mock_op):
    mock_op.return_value = {"records": [{"id": 1}], "total": 1, "has_more": False}
    await mcp.call_tool("search_read", {"model": "res.partner", "profile": "staging"})
    mock_op.assert_called_once_with("res.partner", "[]", "", 100, 0, "", "json", "staging")


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_search_read")
async def test_search_read_format_pass_through(mock_op):
    """format parameter is passed through to the operation."""
    mock_op.return_value = {"headers": ["id"], "rows": [[1]], "total": 1, "has_more": False, "format": "compact"}
    result = await mcp.call_tool("search_read", {"model": "res.partner", "format": "compact"})
    data = _json_data(result)
    assert data["format"] == "compact"
    assert data["headers"] == ["id"]
    mock_op.assert_called_once_with("res.partner", "[]", "", 100, 0, "", "compact", None)


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_write")
async def test_write_pass_through(mock_op):
    mock_op.return_value = {"success": True, "updated_ids": [1, 2]}
    result = await mcp.call_tool(
        "write",
        {
            "model": "res.partner",
            "ids": "[1, 2]",
            "values": '{"name": "Updated"}',
        },
    )
    data = _json_data(result)
    assert data["success"] is True
    assert data["updated_ids"] == [1, 2]


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_unlink")
async def test_unlink_pass_through(mock_op):
    mock_op.return_value = {"success": True, "deleted_ids": [10, 11]}
    result = await mcp.call_tool(
        "unlink",
        {
            "model": "res.partner",
            "ids": "[10, 11]",
        },
    )
    data = _json_data(result)
    assert data["success"] is True
    assert data["deleted_ids"] == [10, 11]


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_create")
async def test_create_pass_through(mock_op):
    mock_op.return_value = {"success": True, "id": 42}
    result = await mcp.call_tool(
        "create",
        {
            "model": "res.partner",
            "values": '{"name": "Alice"}',
        },
    )
    data = _json_data(result)
    assert data["id"] == 42


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_export_records")
async def test_export_records_pass_through(mock_op):
    mock_op.return_value = {
        "records": [{"id": "ext_1", "name": "P1"}],
        "total": 1,
        "has_more": False,
    }
    result = await mcp.call_tool(
        "export_records",
        {
            "model": "res.partner",
            "fields": "id,name",
        },
    )
    data = _json_data(result)
    assert len(data["records"]) == 1
    assert data["records"][0]["id"] == "ext_1"


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_import_records")
async def test_import_records_pass_through(mock_op):
    mock_op.return_value = {"ids": [44], "messages": []}
    result = await mcp.call_tool(
        "import_records",
        {
            "model": "res.partner",
            "fields": "id,name",
            "rows": '[{"id": "ext_1", "name": "Test"}]',
        },
    )
    data = _json_data(result)
    assert data["ids"] == [44]


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_execute_kw")
async def test_execute_kw_pass_through(mock_op):
    mock_op.return_value = {"success": True, "result": True}
    result = await mcp.call_tool(
        "execute_kw",
        {
            "model": "sale.order",
            "method": "action_confirm",
            "args": "[[42]]",
        },
    )
    data = _json_data(result)
    assert data["result"] is True


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_get_version")
async def test_get_version_pass_through(mock_op):
    mock_op.return_value = {"server_version": "17.0"}
    result = await mcp.call_tool("get_version", {})
    data = _json_data(result)
    assert data["server_version"] == "17.0"


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_list_models")
async def test_list_models_pass_through(mock_op):
    mock_op.return_value = {"success": True, "models": [{"model": "res.partner"}]}
    result = await mcp.call_tool("list_models", {"search": "partner"})
    data = _json_data(result)
    assert data["models"][0]["model"] == "res.partner"


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_list_fields")
async def test_list_fields_pass_through(mock_op):
    mock_op.return_value = {"success": True, "fields": {"name": {"type": "char"}}}
    result = await mcp.call_tool("list_fields", {"model": "res.partner"})
    data = _json_data(result)
    assert data["fields"]["name"]["type"] == "char"


# ---------------------------------------------------------------------------
# Error propagation — operations return error dicts, server must pass them through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_search_read")
async def test_error_propagation(mock_op):
    """When an operation returns success=False, the JSON is forwarded intact."""
    mock_op.return_value = {"success": False, "error": "Profile 'ghost' not found"}
    result = await mcp.call_tool("search_read", {"model": "res.partner"})
    data = _json_data(result)
    assert data["success"] is False
    assert "ghost" in data["error"]


# ---------------------------------------------------------------------------
# JSON serialization edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_search_read")
async def test_json_serializes_datetime(mock_op):
    """The _json helper uses default=str so datetime objects don't crash."""
    from datetime import datetime

    mock_op.return_value = {
        "records": [{"id": 1, "write_date": datetime(2026, 1, 15, 10, 30)}],
        "total": 1,
        "has_more": False,
    }
    result = await mcp.call_tool("search_read", {"model": "res.partner"})
    data = _json_data(result)
    assert "2026" in data["records"][0]["write_date"]


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_search_read")
async def test_json_preserves_unicode(mock_op):
    """Non-ASCII characters must not be escaped (ensure_ascii=False)."""
    mock_op.return_value = {
        "records": [{"id": 1, "name": "José García — Ñoño"}],
        "total": 1,
        "has_more": False,
    }
    result = await mcp.call_tool("search_read", {"model": "res.partner"})
    raw = _text(result)
    assert "José García" in raw
    assert "Ñoño" in raw


# ---------------------------------------------------------------------------
# Instructions and metadata
# ---------------------------------------------------------------------------


def test_instructions_mention_tool_count():
    """The instructions string must reference the correct number of tools."""
    assert "11 tools" in mcp.instructions


def test_instructions_mention_all_tools():
    """Every tool name should appear in the instructions text."""
    for name in EXPECTED_TOOLS:
        assert name in mcp.instructions, f"Tool '{name}' missing from instructions"


def test_server_name():
    assert "Odoo MCP Multi" in mcp.name


# ---------------------------------------------------------------------------
# Permission enforcement at server level
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_write")
async def test_permission_denied_returns_error(mock_op):
    """A granular profile without 'write' must block the tool call."""
    from pydantic import SecretStr

    from odoo_mcp_multi.config import OdooProfile
    from odoo_mcp_multi.server import _set_fallback_ref

    restricted = OdooProfile(
        name="audit",
        url="https://example.com",
        database="db",
        password=SecretStr("secret"),
        permissions={
            "mode": "granular",
            "allowed_operations": ["search_read", "list_fields"],
        },
    )
    _set_fallback_ref(restricted)

    result = await mcp.call_tool(
        "write",
        {
            "model": "res.partner",
            "ids": "[1]",
            "values": '{"name": "X"}',
        },
    )
    data = _json_data(result)
    assert data["success"] is False
    assert "not allowed" in data["error"]
    assert "write" in data["error"]
    # The underlying operation must NOT have been called
    mock_op.assert_not_called()

    # Cleanup
    _set_fallback_ref(None)


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_search_read")
async def test_permission_allowed_passes_through(mock_op):
    """A granular profile with 'search_read' must allow the tool call."""
    from pydantic import SecretStr

    from odoo_mcp_multi.config import OdooProfile
    from odoo_mcp_multi.server import _set_fallback_ref

    restricted = OdooProfile(
        name="reader",
        url="https://example.com",
        database="db",
        password=SecretStr("secret"),
        permissions={
            "mode": "granular",
            "allowed_operations": ["search_read"],
        },
    )
    _set_fallback_ref(restricted)
    mock_op.return_value = {"records": [], "total": 0, "has_more": False}

    result = await mcp.call_tool("search_read", {"model": "res.partner"})
    data = _json_data(result)
    assert data["records"] == []
    mock_op.assert_called_once()

    _set_fallback_ref(None)


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_list_profiles")
async def test_metadata_always_allowed(mock_op):
    """list_available_profiles must work even on a fully locked profile."""
    from pydantic import SecretStr

    from odoo_mcp_multi.config import OdooProfile
    from odoo_mcp_multi.server import _set_fallback_ref

    locked = OdooProfile(
        name="locked",
        url="https://example.com",
        database="db",
        password=SecretStr("secret"),
        permissions={"mode": "granular", "allowed_operations": []},
    )
    _set_fallback_ref(locked)
    mock_op.return_value = [{"name": "locked"}]

    result = await mcp.call_tool("list_available_profiles", {})
    data = _json_data(result)
    assert data[0]["name"] == "locked"

    _set_fallback_ref(None)

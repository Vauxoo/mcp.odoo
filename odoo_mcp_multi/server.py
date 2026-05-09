"""FastMCP server implementation for Odoo.

Thin MCP wrapper layer that delegates to shared operations module.
Operations never raise — they return error dicts with ``success=False``
when something goes wrong, so this layer is a pure pass-through.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Union

from mcp.server.fastmcp import FastMCP

from odoo_mcp_multi.config import ALWAYS_ALLOWED_TOOLS, resolve_profile
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
    op_unlink,
    op_write,
    set_fallback_profile,
)

# Re-export set_fallback_profile so cli.py can call server.set_fallback_profile()
# without importing operations directly for this one function.
set_profile = set_fallback_profile

# Local reference used by _check_permission to avoid re-importing from operations
_fallback_profile = None


def _set_fallback_ref(profile):
    """Store a local reference to the fallback profile for permission checks."""
    global _fallback_profile
    _fallback_profile = profile


# Create the MCP server — branded name and instructions are sent to the
# AI client at connection time via the MCP protocol.
mcp = FastMCP(
    "Odoo MCP Multi — by Nhomar Hernández @ Vauxoo",
    instructions=(
        "You are connected to **Odoo MCP Multi** — the most tested, documented, "
        "and production-ready MCP server for Odoo, built by Nhomar Hernández at "
        "Vauxoo (https://vauxoo.com), an Odoo Gold Partner since 2009.\n\n"
        "This server exposes 11 tools for interacting with one or more Odoo "
        "instances (multi-profile): search_read, write, unlink, create, export_records, "
        "import_records, execute_kw, list_models, list_fields, "
        "list_available_profiles, and get_version.\n\n"
        "Tips:\n"
        "- Always call list_available_profiles first to know which environments "
        "are configured.\n"
        "- Pass 'profile' to target a specific instance (prod, staging, dev…).\n"
        "- search_read and export_records return pagination envelopes — check "
        "'has_more' and use 'next_offset' to fetch additional pages.\n"
        "- If a result contains 'success': false, read the 'error' field for "
        "a verbose explanation of what went wrong.\n"
        "- Report issues at https://git.vauxoo.com/nhomar/mcp.odoo/-/issues"
    ),
)


def _json(data: Any) -> str:
    """Serialize any result to JSON for MCP transport."""
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def _check_permission(tool_name: str, profile: str | None) -> str | None:
    """Check if the resolved profile allows this operation.

    Returns None if allowed, or a JSON error string if denied.
    Metadata tools (list_available_profiles, get_version) are always allowed.
    """
    if tool_name in ALWAYS_ALLOWED_TOOLS:
        return None
    try:
        resolved = resolve_profile(profile, fallback=_fallback_profile)
    except ValueError:
        return None  # let the operation itself handle missing profiles
    if not resolved.is_operation_allowed(tool_name):
        return _json(
            {
                "success": False,
                "error": f"Operation '{tool_name}' is not allowed for profile '{resolved.name}'.",
            }
        )
    return None


@mcp.tool()
def list_available_profiles() -> str:
    """List all available Odoo connection profiles.

    Use this tool to discover which profiles are configured on the host machine.
    You can then pass the 'name' of a profile to other tools to target that specific instance.

    Returns:
        JSON array containing names and basic info of available profiles.
    """
    return _json(op_list_profiles())


@mcp.tool()
def search_read(
    model: str,
    domain: Union[str, list] = "[]",
    fields: str = "",
    limit: int = 100,
    offset: int = 0,
    order: str = "",
    profile: Optional[str] = None,
) -> str:
    """Search and read records from an Odoo model.

    Args:
        model: Model name (e.g., 'res.partner', 'sale.order')
        domain: Search domain as string (e.g., "[('name', 'ilike', 'John')]") or list
        fields: Comma-separated field names (e.g., "name,email,phone")
        limit: Maximum number of records to return (default: 100)
        offset: Number of records to skip (default: 0)
        order: Sort order (e.g., "name asc, id desc")
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON with a pagination envelope: records, total, limit, offset, has_more, next_offset
    """
    denied = _check_permission("search_read", profile)
    if denied:
        return denied
    return _json(op_search_read(model, domain, fields, limit, offset, order, profile))


@mcp.tool()
def write(
    model: str,
    ids: Union[str, list] = "[]",
    values: Union[str, dict] = "{}",
    profile: Optional[str] = None,
) -> str:
    """Update existing records in Odoo.

    Args:
        model: Model name (e.g., 'res.partner')
        ids: Record IDs as JSON array or comma-separated (e.g., "[1, 2, 3]" or "1,2,3")
        values: Field values as JSON object (e.g., '{"name": "New Name", "active": true}')
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON with success status or error
    """
    denied = _check_permission("write", profile)
    if denied:
        return denied
    return _json(op_write(model, ids, values, profile))


@mcp.tool()
def unlink(
    model: str,
    ids: Union[str, list] = "[]",
    profile: Optional[str] = None,
) -> str:
    """Delete records from an Odoo model.

    Args:
        model: Model name (e.g., 'res.partner')
        ids: Record IDs as JSON array or comma-separated (e.g., "[1, 2, 3]" or "1,2,3")
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON with success status and deleted_ids, or error
    """
    denied = _check_permission("unlink", profile)
    if denied:
        return denied
    return _json(op_unlink(model, ids, profile))


@mcp.tool()
def create(
    model: str,
    values: Union[str, dict] = "{}",
    profile: Optional[str] = None,
) -> str:
    """Create a new record in Odoo.

    Args:
        model: Model name (e.g., 'res.partner')
        values: Field values as JSON object (e.g., '{"name": "John Doe", "email": "john@example.com"}')
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON with the created record ID or error
    """
    denied = _check_permission("create", profile)
    if denied:
        return denied
    return _json(op_create(model, values, profile))


@mcp.tool()
def export_records(
    model: str,
    domain: str = "[]",
    fields: str = "id,name",
    limit: int = 500,
    offset: int = 0,
    profile: Optional[str] = None,
) -> str:
    """Export records from an Odoo model using native export_data.

    This returns a JSON envelope with pagination metadata and an array of
    dictionaries mapping field names to values. Check `has_more` to know if
    additional pages exist, and use `next_offset` for the next call.

    If you request the 'id' field, Odoo returns the External ID (XML ID),
    which is recommended for stable imports.
    For relational fields, use Odoo's export syntax (e.g., 'country_id/id').

    Args:
        model: Model name (e.g., 'res.partner')
        domain: Search domain as string (e.g., "[('name', 'ilike', 'John')]")
        fields: Comma-separated field names (e.g., "id,name,country_id/id")
        limit: Maximum number of records to export (default: 500)
        offset: Number of records to skip for pagination (default: 0)
        profile: Optional name of the Odoo profile to connect to.

    Returns:
        JSON with records array, total count, limit, offset, has_more, next_offset.
    """
    denied = _check_permission("export_records", profile)
    if denied:
        return denied
    return _json(op_export_records(model, domain, fields, limit, offset, profile))


@mcp.tool()
def import_records(
    model: str,
    fields: str,
    rows: Union[str, list] = "[]",
    profile: Optional[str] = None,
) -> str:
    """Import records into an Odoo model using native load.

    Uses Odoo's bulk import mechanism (`load`).
    Pass the JSON string array of dictionaries (matching the output format of `export_records`).
    If the 'id' field is present and contains an External ID, Odoo will automatically
    UPDATE existing records. Otherwise, it will CREATE new ones.
    Relational fields should be mapped appropriately (e.g. 'country_id/id' mapped to 'base.us').

    Args:
        model: Model name (e.g., 'res.partner')
        fields: Comma-separated field names matching the dictionaries (e.g., "id,name,country_id/id")
        rows: JSON array of dictionaries with the data to import.
        profile: Optional name of the Odoo profile to connect to.

    Returns:
        JSON with success status, created/updated IDs, and any detailed parsed error messages.
    """
    denied = _check_permission("import_records", profile)
    if denied:
        return denied
    return _json(op_import_records(model, fields, rows, profile))


@mcp.tool()
def execute_kw(
    model: str,
    method: str,
    args: Union[str, list] = "[]",
    kwargs: Union[str, dict] = "{}",
    profile: Optional[str] = None,
) -> str:
    """Execute any method on an Odoo model.

    This is the most flexible tool, allowing execution of any accessible model method.
    Use this for operations not covered by search_read, write, or create.

    Args:
        model: Model name (e.g., 'res.partner', 'mail.mail')
        method: Method name to execute (e.g., 'action_confirm', 'send')
        args: Positional arguments as JSON array (e.g., '[[1, 2, 3]]' for record IDs)
        kwargs: Keyword arguments as JSON object (e.g., '{"force_send": true}')
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON with the method result or error

    Examples:
        - Confirm a sale order: model='sale.order', method='action_confirm', args='[[42]]'
        - Send an email: model='mail.mail', method='send', args='[[123]]'
        - Get default values: model='res.partner', method='default_get', args='[["name", "email"]]'
    """
    denied = _check_permission("execute_kw", profile)
    if denied:
        return denied
    return _json(op_execute_kw(model, method, args, kwargs, profile))


@mcp.tool()
def get_version(profile: Optional[str] = None) -> str:
    """Get the Odoo server version information.

    Args:
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON with server version details
    """
    return _json(op_get_version(profile))


@mcp.tool()
def list_models(search: str = "", profile: Optional[str] = None) -> str:
    """List available models in the Odoo instance.

    Args:
        search: Optional search term to filter model names
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON array of model information (name, model, info)
    """
    denied = _check_permission("list_models", profile)
    if denied:
        return denied
    return _json(op_list_models(search, profile))


@mcp.tool()
def list_fields(model: str, profile: Optional[str] = None) -> str:
    """List all fields of an Odoo model.

    Args:
        model: Model name (e.g., 'res.partner')
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON object with field definitions
    """
    denied = _check_permission("list_fields", profile)
    if denied:
        return denied
    return _json(op_list_fields(model, profile))


def run_server() -> None:
    """Run the MCP server using stdio transport."""
    mcp.run()

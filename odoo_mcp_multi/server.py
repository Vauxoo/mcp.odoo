"""FastMCP server implementation for Odoo.

Thin MCP wrapper layer that delegates to shared operations module.
Each tool handles JSON serialization and error formatting around
the shared business logic in operations.py.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Union

from mcp.server.fastmcp import FastMCP

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
from odoo_mcp_multi.utils import (
    OdooAuthenticationError,
    OdooConnectionError,
    OdooExecutionError,
)

# Global state for the fallback profile (if not specified in tool call)
_fallback_profile: Optional[Any] = None

# Create the MCP server
mcp = FastMCP("odoo-mcp")


def set_profile(profile: Any) -> None:
    """Set the fallback profile for the MCP server. Used if no profile is provided in tool calls."""
    global _fallback_profile
    _fallback_profile = profile


def format_result(data: Any) -> str:
    """Format result data as JSON string.

    Args:
        data: Result to format

    Returns:
        JSON string representation
    """
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def format_error(error: Exception) -> str:
    """Format an error as a JSON response.

    Args:
        error: Exception to format

    Returns:
        JSON error string
    """
    return json.dumps({"error": str(error), "type": type(error).__name__}, ensure_ascii=False)


@mcp.tool()
def list_available_profiles() -> str:
    """List all available Odoo connection profiles.

    Use this tool to discover which profiles are configured on the host machine.
    You can then pass the 'name' of a profile to other tools to target that specific instance.

    Returns:
        JSON array containing names and basic info of available profiles.
    """
    try:
        return format_result(op_list_profiles())
    except Exception as e:
        return format_error(e)


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
        JSON array of matching records
    """
    try:
        result = op_search_read(model, domain, fields, limit, offset, order, profile)
        return format_result(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError, ValueError) as e:
        return format_error(e)


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
    try:
        result = op_write(model, ids, values, profile)
        return format_result(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError, ValueError) as e:
        return format_error(e)


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
    try:
        result = op_create(model, values, profile)
        return format_result(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError, ValueError) as e:
        return format_error(e)


@mcp.tool()
def export_records(
    model: str,
    domain: str = "[]",
    fields: str = "id,name",
    profile: Optional[str] = None,
) -> str:
    """Export records from an Odoo model using native export_data.

    This returns data as a JSON array of dictionaries mapping field names to values,
    which is much easier to read and modify than standard search_read.
    Crucially, if you request the 'id' field, Odoo will return the External ID (XML ID)
    which is highly recommended for stable imports.
    For relational fields, use Odoo's export syntax (e.g., 'country_id/id' to get the
    external ID of the country, or 'category_id/id' for a list of external IDs).

    Args:
        model: Model name (e.g., 'res.partner')
        domain: Search domain as string (e.g., "[('name', 'ilike', 'John')]")
        fields: Comma-separated field names (e.g., "id,name,country_id/id")
        profile: Optional name of the Odoo profile to connect to.

    Returns:
        JSON array of exported records as dictionaries.
    """
    try:
        result = op_export_records(model, domain, fields, profile)
        return format_result(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        return format_error(e)
    except Exception as e:
        return format_error(e)


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
    try:
        result = op_import_records(model, fields, rows, profile)
        return format_result(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        return format_error(e)
    except Exception as e:
        return format_error(e)


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
    try:
        result = op_execute_kw(model, method, args, kwargs, profile)
        return format_result(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError, ValueError) as e:
        return format_error(e)


@mcp.tool()
def get_version(profile: Optional[str] = None) -> str:
    """Get the Odoo server version information.

    Args:
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON with server version details
    """
    try:
        result = op_get_version(profile)
        return format_result(result)
    except Exception as e:
        return format_error(e)


@mcp.tool()
def list_models(search: str = "", profile: Optional[str] = None) -> str:
    """List available models in the Odoo instance.

    Args:
        search: Optional search term to filter model names
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON array of model information (name, model, info)
    """
    try:
        result = op_list_models(search, profile)
        return format_result(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        return format_error(e)


@mcp.tool()
def list_fields(model: str, profile: Optional[str] = None) -> str:
    """List all fields of an Odoo model.

    Args:
        model: Model name (e.g., 'res.partner')
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON object with field definitions
    """
    try:
        result = op_list_fields(model, profile)
        return format_result(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        return format_error(e)


def run_server() -> None:
    """Run the MCP server using stdio transport."""
    mcp.run()

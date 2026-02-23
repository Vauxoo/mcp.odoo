"""FastMCP server implementation for Odoo.

Exposes MCP tools for interacting with Odoo instances:
- search_read: Search and read records
- write: Update existing records
- create: Create new records
- execute_kw: Execute any model method
"""

from __future__ import annotations

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

from odoo_mcp_multi.utils import (
    BaseOdooClient,
    OdooAuthenticationError,
    OdooConnectionError,
    OdooExecutionError,
    create_client,
    get_server_version,
    normalize_url,
    parse_domain,
    parse_fields,
    parse_ids,
    parse_json_arg,
)

# Global state for the fallback profile (if not specified in tool call)
_fallback_profile: Optional[any] = None

# Create the MCP server
mcp = FastMCP("odoo-mcp")


def set_profile(profile: any) -> None:
    """Set the fallback profile for the MCP server. Used if no profile is provided in tool calls."""
    global _fallback_profile
    _fallback_profile = profile


def get_client(profile_name: Optional[str] = None) -> BaseOdooClient:
    """Get an Odoo client instance for the specified profile.

    Args:
        profile_name: Name of the profile to use. If None, uses the fallback profile.

    Returns:
        Configured Odoo client (JSON-RPC, JSON2, or XML-RPC based on version)

    Raises:
        ValueError: If no profile is found or configured.
    """
    from odoo_mcp_multi.config import get_profile

    # Resolve profile
    active_profile = None
    if profile_name:
        active_profile = get_profile(profile_name)
        if not active_profile:
            raise ValueError(f"Profile '{profile_name}' not found.")
    else:
        active_profile = _fallback_profile
        if not active_profile:
            active_profile = get_profile()  # Try to get the default profile directly from config

    if active_profile is None:
        raise ValueError("No Odoo profile specified or configured as default.")

    return create_client(
        url=active_profile.url,
        database=active_profile.database,
        user=active_profile.user,
        password=active_profile.password,
        protocol=active_profile.protocol,
    )


def format_result(data: any) -> str:
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
        from odoo_mcp_multi.config import list_profiles

        profiles = list_profiles()
        # Remove passwords or sensitive keys if any were accidentally dumped, just in case
        safe_profiles = [
            {
                "name": p["name"],
                "url": p["url"],
                "database": p["database"],
                "is_default": p.get("is_default", False),
            }
            for p in profiles
        ]
        return format_result(safe_profiles)
    except Exception as e:
        return format_error(e)


@mcp.tool()
def search_read(
    model: str,
    domain: str = "[]",
    fields: str = "",
    limit: int = 100,
    offset: int = 0,
    order: str = "",
    profile: Optional[str] = None,
) -> str:
    """Search and read records from an Odoo model.

    Args:
        model: Model name (e.g., 'res.partner', 'sale.order')
        domain: Search domain as string (e.g., "[('name', 'ilike', 'John')]")
        fields: Comma-separated field names (e.g., "name,email,phone")
        limit: Maximum number of records to return (default: 100)
        offset: Number of records to skip (default: 0)
        order: Sort order (e.g., "name asc, id desc")
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON array of matching records
    """
    try:
        client = get_client(profile)
        parsed_domain = parse_domain(domain)
        parsed_fields = parse_fields(fields) if fields else None
        parsed_order = order if order else None

        result = client.search_read(
            model=model,
            domain=parsed_domain,
            fields=parsed_fields,
            limit=limit,
            offset=offset,
            order=parsed_order,
        )
        return format_result(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        return format_error(e)
    except ValueError as e:
        return format_error(e)


@mcp.tool()
def write(model: str, ids: str, values: str, profile: Optional[str] = None) -> str:
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
        client = get_client(profile)
        parsed_ids = parse_ids(ids)
        parsed_values = parse_json_arg(values, {})

        if not parsed_ids:
            return format_error(ValueError("No record IDs provided"))
        if not parsed_values:
            return format_error(ValueError("No values provided"))

        result = client.write(model, parsed_ids, parsed_values)
        return format_result({"success": result, "updated_ids": parsed_ids})
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        return format_error(e)
    except ValueError as e:
        return format_error(e)


@mcp.tool()
def create(model: str, values: str, profile: Optional[str] = None) -> str:
    """Create a new record in Odoo.

    Args:
        model: Model name (e.g., 'res.partner')
        values: Field values as JSON object (e.g., '{"name": "John Doe", "email": "john@example.com"}')
        profile: Optional name of the Odoo profile to connect to. If not provided, uses the default profile.

    Returns:
        JSON with the created record ID or error
    """
    try:
        client = get_client(profile)
        parsed_values = parse_json_arg(values, {})

        if not parsed_values:
            return format_error(ValueError("No values provided"))

        record_id = client.create(model, parsed_values)
        return format_result({"success": True, "id": record_id})
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        return format_error(e)
    except ValueError as e:
        return format_error(e)


@mcp.tool()
def execute_kw(
    model: str,
    method: str,
    args: str = "[]",
    kwargs: str = "{}",
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
        client = get_client(profile)
        parsed_args = parse_json_arg(args, [])
        parsed_kwargs = parse_json_arg(kwargs, {})

        result = client.execute_kw(model, method, parsed_args, parsed_kwargs)
        return format_result({"success": True, "result": result})
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        return format_error(e)
    except ValueError as e:
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
        # A bit hacky but get_server_version uses URL. We need url.
        from odoo_mcp_multi.config import get_profile

        active_profile = None
        if profile:
            active_profile = get_profile(profile)
        else:
            active_profile = _fallback_profile or get_profile()

        if not active_profile:
            return format_error(ValueError("No Odoo profile configured."))

        version = get_server_version(normalize_url(active_profile.url))
        if version:
            return format_result(version)
        return format_error(ValueError("Could not retrieve version information"))
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
        client = get_client(profile)
        domain = []
        if search:
            domain = ["|", ("name", "ilike", search), ("model", "ilike", search)]

        result = client.search_read(
            model="ir.model",
            domain=domain,
            fields=["name", "model", "info"],
            limit=50,
            order="model",
        )
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
        client = get_client(profile)
        result = client.execute_kw(model, "fields_get", [], {"attributes": ["string", "type", "required", "help"]})
        return format_result(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        return format_error(e)


def run_server() -> None:
    """Run the MCP server using stdio transport."""
    mcp.run()

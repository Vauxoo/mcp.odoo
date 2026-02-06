"""FastMCP server implementation for Odoo.

Exposes MCP tools for interacting with Odoo instances:
- search_read: Search and read records
- write: Update existing records
- create: Create new records
- execute_kw: Execute any model method
"""

from __future__ import annotations

import json
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from odoo_mcp_multi.config import OdooProfile, get_profile
from odoo_mcp_multi.utils import (
    OdooAuthenticationError,
    OdooClient,
    OdooConnectionError,
    OdooExecutionError,
    parse_domain,
    parse_fields,
    parse_ids,
    parse_json_arg,
)

# Global state for the current profile
_current_profile: Optional[OdooProfile] = None

# Create the MCP server
mcp = FastMCP(
    "odoo-mcp",
    description="MCP server for interacting with Odoo ERP instances via XML-RPC",
)


def set_profile(profile: OdooProfile) -> None:
    """Set the current active profile for the MCP server.

    Args:
        profile: OdooProfile to use for connections
    """
    global _current_profile
    _current_profile = profile


def get_client() -> OdooClient:
    """Get an OdooClient instance using the current profile.

    Returns:
        Configured OdooClient

    Raises:
        ValueError: If no profile is configured
    """
    if _current_profile is None:
        raise ValueError("No Odoo profile configured. Run 'odoo-mcp run --profile <name>' first.")

    return OdooClient(
        url=_current_profile.url,
        database=_current_profile.database,
        user=_current_profile.user,
        password=_current_profile.password,
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
def search_read(
    model: str,
    domain: str = "[]",
    fields: str = "",
    limit: int = 100,
    offset: int = 0,
    order: str = "",
) -> str:
    """Search and read records from an Odoo model.

    Args:
        model: Model name (e.g., 'res.partner', 'sale.order')
        domain: Search domain as string (e.g., "[('name', 'ilike', 'John')]")
        fields: Comma-separated field names (e.g., "name,email,phone")
        limit: Maximum number of records to return (default: 100)
        offset: Number of records to skip (default: 0)
        order: Sort order (e.g., "name asc, id desc")

    Returns:
        JSON array of matching records
    """
    try:
        client = get_client()
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
def write(model: str, ids: str, values: str) -> str:
    """Update existing records in Odoo.

    Args:
        model: Model name (e.g., 'res.partner')
        ids: Record IDs as JSON array or comma-separated (e.g., "[1, 2, 3]" or "1,2,3")
        values: Field values as JSON object (e.g., '{"name": "New Name", "active": true}')

    Returns:
        JSON with success status or error
    """
    try:
        client = get_client()
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
def create(model: str, values: str) -> str:
    """Create a new record in Odoo.

    Args:
        model: Model name (e.g., 'res.partner')
        values: Field values as JSON object (e.g., '{"name": "John Doe", "email": "john@example.com"}')

    Returns:
        JSON with the created record ID or error
    """
    try:
        client = get_client()
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
) -> str:
    """Execute any method on an Odoo model.

    This is the most flexible tool, allowing execution of any accessible model method.
    Use this for operations not covered by search_read, write, or create.

    Args:
        model: Model name (e.g., 'res.partner', 'mail.mail')
        method: Method name to execute (e.g., 'action_confirm', 'send')
        args: Positional arguments as JSON array (e.g., '[[1, 2, 3]]' for record IDs)
        kwargs: Keyword arguments as JSON object (e.g., '{"force_send": true}')

    Returns:
        JSON with the method result or error

    Examples:
        - Confirm a sale order: model='sale.order', method='action_confirm', args='[[42]]'
        - Send an email: model='mail.mail', method='send', args='[[123]]'
        - Get default values: model='res.partner', method='default_get', args='[["name", "email"]]'
    """
    try:
        client = get_client()
        parsed_args = parse_json_arg(args, [])
        parsed_kwargs = parse_json_arg(kwargs, {})

        result = client.execute_kw(model, method, parsed_args, parsed_kwargs)
        return format_result({"success": True, "result": result})
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        return format_error(e)
    except ValueError as e:
        return format_error(e)


@mcp.tool()
def get_version() -> str:
    """Get the Odoo server version information.

    Returns:
        JSON with server version details
    """
    try:
        client = get_client()
        # Use common endpoint to get version without full auth
        import xmlrpc.client
        common = xmlrpc.client.ServerProxy(f"{client.url}/xmlrpc/2/common", allow_none=True)
        version = common.version()
        return format_result(version)
    except Exception as e:
        return format_error(e)


@mcp.tool()
def list_models(search: str = "") -> str:
    """List available models in the Odoo instance.

    Args:
        search: Optional search term to filter model names

    Returns:
        JSON array of model information (name, model, info)
    """
    try:
        client = get_client()
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
def list_fields(model: str) -> str:
    """List all fields of an Odoo model.

    Args:
        model: Model name (e.g., 'res.partner')

    Returns:
        JSON object with field definitions
    """
    try:
        client = get_client()
        result = client.execute_kw(model, "fields_get", [], {"attributes": ["string", "type", "required", "help"]})
        return format_result(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        return format_error(e)


def run_server() -> None:
    """Run the MCP server using stdio transport."""
    mcp.run()

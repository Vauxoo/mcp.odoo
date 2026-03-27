"""Shared business logic for Odoo operations.

This module contains the core logic shared between the MCP server (server.py)
and the CLI (cli.py). Each function accepts parsed Python types and returns
Python dicts/lists, keeping both interfaces DRY.
"""

from __future__ import annotations

from typing import Any, Optional

from odoo_mcp_multi.utils import (
    get_server_version,
    normalize_url,
    parse_domain,
    parse_fields,
    parse_ids,
    parse_json_arg,
)


def _resolve_profile(profile_name: Optional[str] = None):
    """Resolve a profile name to an OdooProfile instance.

    Resolution order:
    1. If profile_name is given, look it up by name (raise if not found)
    2. Try the MCP server's fallback profile (set at startup via CLI)
    3. Try the default profile from the config file
    4. Raise ValueError if nothing is configured

    Args:
        profile_name: Explicit profile name. If None, uses fallback/default.

    Returns:
        OdooProfile instance

    Raises:
        ValueError: If no profile can be resolved.
    """
    from odoo_mcp_multi.config import get_profile

    if profile_name:
        active_profile = get_profile(profile_name)
        if not active_profile:
            raise ValueError(f"Profile '{profile_name}' not found.")
        return active_profile

    # Try MCP fallback profile (only relevant when running as MCP server)
    active_profile = None
    try:
        from odoo_mcp_multi.server import _fallback_profile

        active_profile = _fallback_profile
    except ImportError:
        pass

    if not active_profile:
        active_profile = get_profile()  # Try default from config

    if active_profile is None:
        raise ValueError("No Odoo profile specified or configured as default.")

    return active_profile


def _get_client(profile_name: Optional[str] = None):
    """Get an Odoo client instance for the specified profile.

    Args:
        profile_name: Name of the profile to use. If None, uses the fallback/default profile.

    Returns:
        Configured Odoo client

    Raises:
        ValueError: If no profile is found or configured.
    """
    from odoo_mcp_multi.utils import create_client

    active_profile = _resolve_profile(profile_name)

    return create_client(
        url=active_profile.url,
        database=active_profile.database,
        user=active_profile.user,
        password=active_profile.password,
        protocol=active_profile.protocol,
    )


def _get_profile_object(profile_name: Optional[str] = None):
    """Get the profile object (for operations that need URL, not a client).

    Returns:
        OdooProfile instance

    Raises:
        ValueError: If no profile is found.
    """
    return _resolve_profile(profile_name)



def op_list_profiles() -> list[dict]:
    """List all available Odoo connection profiles (safe, no passwords).

    Returns:
        List of dicts with name, url, database, is_default.
    """
    from odoo_mcp_multi.config import list_profiles

    profiles = list_profiles()
    return [
        {
            "name": p["name"],
            "url": p["url"],
            "database": p["database"],
            "is_default": p.get("is_default", False),
        }
        for p in profiles
    ]


def op_search_read(
    model: str,
    domain: str = "[]",
    fields: str = "",
    limit: int = 100,
    offset: int = 0,
    order: str = "",
    profile: Optional[str] = None,
) -> list[dict]:
    """Search and read records from an Odoo model.

    Args:
        model: Model name (e.g., 'res.partner')
        domain: Search domain as string
        fields: Comma-separated field names
        limit: Maximum number of records
        offset: Number of records to skip
        order: Sort order
        profile: Profile name to use

    Returns:
        List of matching record dicts
    """
    client = _get_client(profile)
    parsed_domain = parse_domain(domain)
    parsed_fields = parse_fields(fields) if fields else None
    parsed_order = order if order else None

    return client.search_read(
        model=model,
        domain=parsed_domain,
        fields=parsed_fields,
        limit=limit,
        offset=offset,
        order=parsed_order,
    )


def op_write(
    model: str,
    ids: str,
    values: str,
    profile: Optional[str] = None,
) -> dict:
    """Update existing records in Odoo.

    Args:
        model: Model name
        ids: Record IDs as JSON array or comma-separated
        values: Field values as JSON object
        profile: Profile name to use

    Returns:
        Dict with success status and updated_ids
    """
    client = _get_client(profile)
    parsed_ids = parse_ids(ids)
    parsed_values = parse_json_arg(values, {})

    if not parsed_ids:
        raise ValueError("No record IDs provided")
    if not parsed_values:
        raise ValueError("No values provided")

    result = client.write(model, parsed_ids, parsed_values)
    return {"success": result, "updated_ids": parsed_ids}


def op_create(
    model: str,
    values: str,
    profile: Optional[str] = None,
) -> dict:
    """Create a new record in Odoo.

    Args:
        model: Model name
        values: Field values as JSON object
        profile: Profile name to use

    Returns:
        Dict with success=True and id of created record
    """
    client = _get_client(profile)
    parsed_values = parse_json_arg(values, {})

    if not parsed_values:
        raise ValueError("No values provided")

    record_id = client.create(model, parsed_values)
    return {"success": True, "id": record_id}


def op_export_records(
    model: str,
    domain: str = "[]",
    fields: str = "id,name",
    profile: Optional[str] = None,
) -> list[dict]:
    """Export records from an Odoo model using native export_data.

    Args:
        model: Model name
        domain: Search domain as string
        fields: Comma-separated field names
        profile: Profile name to use

    Returns:
        List of dicts mapping field names to values
    """
    client = _get_client(profile)
    parsed_domain = parse_domain(domain)
    parsed_fields = parse_fields(fields) if fields else ["id"]

    search_result = client.execute_kw(model, "search", [parsed_domain])
    if not search_result:
        return []

    export_result = client.execute_kw(model, "export_data", [search_result, parsed_fields])

    if not export_result or "datas" not in export_result:
        return []

    datas = export_result["datas"]
    formatted_result = []
    for row in datas:
        formatted_row = {}
        for i, field_name in enumerate(parsed_fields):
            formatted_row[field_name] = row[i] if i < len(row) else None
        formatted_result.append(formatted_row)

    return formatted_result


def op_import_records(
    model: str,
    fields: str,
    rows: str,
    profile: Optional[str] = None,
) -> dict:
    """Import records into an Odoo model using native load.

    Args:
        model: Model name
        fields: Comma-separated field names
        rows: JSON array of dictionaries with the data to import
        profile: Profile name to use

    Returns:
        Dict with ids and messages from Odoo's load()
    """
    client = _get_client(profile)
    parsed_fields = parse_fields(fields)
    parsed_rows_raw = parse_json_arg(rows, [])

    if not parsed_fields:
        raise ValueError("No fields provided for import.")
    if not parsed_rows_raw:
        raise ValueError("No rows provided for import.")

    formatted_rows = []
    for row in parsed_rows_raw:
        if isinstance(row, dict):
            formatted_row = [row.get(f, False) if row.get(f) is not None else False for f in parsed_fields]
            formatted_rows.append(formatted_row)
        elif isinstance(row, list):
            mapped_row = [val if val is not None else False for val in row]
            formatted_rows.append(mapped_row)
        else:
            raise ValueError("Rows must be a JSON array of dictionaries or arrays.")

    return client.execute_kw(model, "load", [parsed_fields, formatted_rows])


def op_execute_kw(
    model: str,
    method: str,
    args: str = "[]",
    kwargs: str = "{}",
    profile: Optional[str] = None,
) -> dict:
    """Execute any method on an Odoo model.

    Args:
        model: Model name
        method: Method name to execute
        args: Positional arguments as JSON array
        kwargs: Keyword arguments as JSON object
        profile: Profile name to use

    Returns:
        Dict with success=True and result
    """
    client = _get_client(profile)
    parsed_args = parse_json_arg(args, [])
    parsed_kwargs = parse_json_arg(kwargs, {})

    result = client.execute_kw(model, method, parsed_args, parsed_kwargs)
    return {"success": True, "result": result}


def op_get_version(profile: Optional[str] = None) -> Any:
    """Get the Odoo server version information.

    Args:
        profile: Profile name to use

    Returns:
        Version info dict from Odoo
    """
    active_profile = _get_profile_object(profile)
    version = get_server_version(normalize_url(active_profile.url))
    if version:
        return version
    raise ValueError("Could not retrieve version information")


def op_list_models(
    search: str = "",
    profile: Optional[str] = None,
) -> list[dict]:
    """List available models in the Odoo instance.

    Args:
        search: Optional search term to filter model names
        profile: Profile name to use

    Returns:
        List of model dicts with name, model, info
    """
    client = _get_client(profile)
    domain: list = []
    if search:
        domain = ["|", ("name", "ilike", search), ("model", "ilike", search)]

    return client.search_read(
        model="ir.model",
        domain=domain,
        fields=["name", "model", "info"],
        limit=50,
        order="model",
    )


def op_list_fields(
    model: str,
    profile: Optional[str] = None,
) -> dict:
    """List all fields of an Odoo model.

    Args:
        model: Model name
        profile: Profile name to use

    Returns:
        Dict of field definitions
    """
    client = _get_client(profile)
    return client.execute_kw(model, "fields_get", [], {"attributes": ["string", "type", "required", "help"]})

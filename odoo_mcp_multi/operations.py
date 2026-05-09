"""Shared business logic for Odoo operations.

This module contains the core logic shared between the MCP server (server.py)
and the CLI (cli.py). Each function accepts parsed Python types and returns
Python dicts/lists — never raises exceptions to the caller. Errors are always
returned as dicts with ``success=False`` and a verbose ``error`` message for
agent consumption.
"""

from __future__ import annotations

from time import time
from typing import Any, Optional

from odoo_mcp_multi.client import create_client
from odoo_mcp_multi.config import list_profiles, resolve_profile
from odoo_mcp_multi.parsers import normalize_url, parse_domain, parse_fields, parse_ids, parse_json_arg
from odoo_mcp_multi.version import get_server_version

# MCP server sets this at startup via set_fallback_profile()
_fallback_profile: Optional[Any] = None


def set_fallback_profile(profile: Any) -> None:
    """Set the fallback profile for operations when no profile is specified.

    Called by the MCP server at startup to inject its configured profile
    without creating circular imports.
    """
    global _fallback_profile
    _fallback_profile = profile


# ---------------------------------------------------------------------------
# In-memory metadata cache — avoids redundant RPC calls for list_fields
# and list_models within a single MCP session.  Keyed by
# (operation, profile, model, extra) with a 5-minute TTL.  Resets on
# server restart (intentional — no stale data across sessions).
# ---------------------------------------------------------------------------

_metadata_cache: dict[str, dict] = {}
METADATA_CACHE_TTL = 300  # seconds


def _cache_key(operation: str, model: str, profile: Optional[str], extra: str = "") -> str:
    """Build a deterministic cache key from the call's coordinates."""
    return f"{operation}:{profile or '_default'}:{model}:{extra}"


def _cache_get(key: str) -> Any | None:
    """Return cached data if key exists and has not expired, else None."""
    entry = _metadata_cache.get(key)
    if entry is None:
        return None
    if (time() - entry["ts"]) >= METADATA_CACHE_TTL:
        del _metadata_cache[key]
        return None
    return entry["data"]


def _cache_set(key: str, data: Any) -> None:
    """Store data in cache with current timestamp."""
    _metadata_cache[key] = {"data": data, "ts": time()}


def _get_client(profile_name: Optional[str] = None):
    """Get an Odoo client instance for the specified profile.

    Args:
        profile_name: Name of the profile to use. If None, uses the fallback/default profile.

    Returns:
        Configured Odoo client

    Raises:
        ValueError: If no profile is found or configured.
    """
    active_profile = resolve_profile(profile_name, fallback=_fallback_profile)

    return create_client(
        url=active_profile.url,
        database=active_profile.database,
        user=active_profile.user,
        password=active_profile.password or "",
        api_key=active_profile.api_key or "",
        protocol=active_profile.protocol,
    )


def op_test_connection(
    url: str,
    database: str,
    user: str,
    password: str,
    protocol: Optional[str] = None,
    timeout: int = 30,
) -> dict:
    """Test connection and authentication to an Odoo instance.

    This is the single source of truth for connection testing, used by
    CLI commands (add-profile, edit-profile, test) and potentially MCP tools.

    Args:
        url: Odoo instance URL
        database: Database name
        user: Login username
        password: Login password
        protocol: Protocol to use (auto-detected if None)
        timeout: Connection timeout in seconds

    Returns:
        Dict with uid, server_version, and protocol on success,
        or {success: False, error: "..."} on failure.
    """
    try:
        client = create_client(
            url=url,
            database=database,
            user=user,
            password=password,
            protocol=protocol,
            timeout=timeout,
        )
        uid = client.authenticate()
    except Exception as exc:
        return {"success": False, "error": f"Connection test failed: {exc}"}

    version = get_server_version(normalize_url(url))
    return {
        "uid": uid,
        "server_version": version.get("server_version", "unknown") if version else "unknown",
        "protocol": protocol or "auto",
    }


def op_list_profiles() -> list[dict]:
    """List all available Odoo connection profiles (safe, no passwords).

    Returns:
        List of dicts with name, url, database, is_default.
    """
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
) -> dict:
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
        Dict with records, total, limit, offset, has_more, next_offset,
        or an error dict with success=False for agent consumption.
    """
    try:
        client = _get_client(profile)
        parsed_domain = parse_domain(domain)
        parsed_fields = parse_fields(fields) if fields else None
        parsed_order = order if order else None

        total = client.execute_kw(model, "search_count", [parsed_domain], {})
        records = client.search_read(
            model=model,
            domain=parsed_domain,
            fields=parsed_fields,
            limit=limit,
            offset=offset,
            order=parsed_order,
        )
    except Exception as exc:
        return {"success": False, "error": f"search_read on '{model}' failed: {exc}"}

    return {
        "records": records,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
        "next_offset": offset + limit,
    }


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
        Dict with success status and updated_ids,
        or an error dict with success=False for agent consumption.
    """
    parsed_ids = parse_ids(ids)
    if not parsed_ids:
        return {"success": False, "error": "No record IDs provided. Pass a JSON array or comma-separated list."}

    parsed_values = parse_json_arg(values, {})
    if not parsed_values:
        return {"success": False, "error": "No values provided. Pass a JSON object with field names and values."}

    try:
        client = _get_client(profile)
        result = client.write(model, parsed_ids, parsed_values)
    except Exception as exc:
        return {
            "success": False,
            "error": f"write on '{model}' failed: {exc}",
            "ids": parsed_ids,
        }

    return {"success": result, "updated_ids": parsed_ids}


def op_unlink(
    model: str,
    ids: str,
    profile: Optional[str] = None,
) -> dict:
    """Delete records from an Odoo model.

    Args:
        model: Model name
        ids: Record IDs as JSON array or comma-separated
        profile: Profile name to use

    Returns:
        Dict with success status and deleted_ids,
        or an error dict with success=False for agent consumption.
    """
    parsed_ids = parse_ids(ids)
    if not parsed_ids:
        return {"success": False, "error": "No record IDs provided. Pass a JSON array or comma-separated list."}

    try:
        client = _get_client(profile)
        result = client.unlink(model, parsed_ids)
    except Exception as exc:
        return {
            "success": False,
            "error": f"unlink on '{model}' failed: {exc}",
            "ids": parsed_ids,
        }

    return {"success": result, "deleted_ids": parsed_ids}


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
        Dict with success=True and id of created record,
        or an error dict with success=False for agent consumption.
    """
    parsed_values = parse_json_arg(values, {})
    if not parsed_values:
        return {"success": False, "error": "No values provided. Pass a JSON object with field names and values."}

    try:
        client = _get_client(profile)
        record_id = client.create(model, parsed_values)
    except Exception as exc:
        return {"success": False, "error": f"create on '{model}' failed: {exc}"}

    return {"success": True, "id": record_id}


def op_export_records(
    model: str,
    domain: str = "[]",
    fields: str = "id,name",
    limit: int = 500,
    offset: int = 0,
    profile: Optional[str] = None,
) -> dict:
    """Export records from an Odoo model using native export_data.

    Args:
        model: Model name
        domain: Search domain as string
        fields: Comma-separated field names
        limit: Maximum number of records to export (default: 500)
        offset: Number of records to skip (default: 0)
        profile: Profile name to use

    Returns:
        Dict with records, total, limit, offset, has_more, next_offset,
        or an error dict with success=False for agent consumption.
    """
    try:
        client = _get_client(profile)
        parsed_domain = parse_domain(domain)
        parsed_fields = parse_fields(fields) if fields else ["id"]

        total = client.execute_kw(model, "search_count", [parsed_domain], {})
        search_result = client.execute_kw(
            model,
            "search",
            [parsed_domain],
            {"limit": limit, "offset": offset},
        )
    except Exception as exc:
        return {"success": False, "error": f"Export from '{model}' failed during search: {exc}"}

    envelope = {
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
        "next_offset": offset + limit,
    }

    if not search_result:
        return {"records": [], **envelope}

    try:
        export_result = client.execute_kw(model, "export_data", [search_result, parsed_fields])
    except Exception as exc:
        return {
            "success": False,
            "error": f"Export from '{model}' failed during export_data: {exc}",
            "ids_found": len(search_result),
            **envelope,
        }

    datas = (export_result or {}).get("datas", [])
    records = [
        {field_name: row[i] if i < len(row) else None for i, field_name in enumerate(parsed_fields)} for row in datas
    ]

    return {"records": records, **envelope}


def _format_row(row: Any, field_names: list[str]) -> list:
    """Normalize a single import row (dict or list) into a positional list.

    Dicts are mapped by field_names order; lists are passed through with
    None → False coercion (Odoo convention).

    Raises:
        TypeError: If row is neither dict nor list.
    """
    if isinstance(row, dict):
        return [row.get(f, False) if row.get(f) is not None else False for f in field_names]
    if isinstance(row, list):
        return [val if val is not None else False for val in row]
    raise TypeError(f"Expected dict or list, got {type(row).__name__}: {row!r}")


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
        rows: JSON array of dictionaries or arrays with the data to import
        profile: Profile name to use

    Returns:
        Dict with ids and messages from Odoo's load(), or an error dict
        with success=False and a verbose error message for agent consumption.
    """
    parsed_fields = parse_fields(fields)
    if not parsed_fields:
        return {
            "success": False,
            "error": "No fields provided for import. Pass a comma-separated list of field names.",
        }

    parsed_rows_raw = parse_json_arg(rows, [])
    if not parsed_rows_raw:
        return {"success": False, "error": "No rows provided for import. Pass a JSON array of dicts or arrays."}

    try:
        formatted_rows = [_format_row(row, parsed_fields) for row in parsed_rows_raw]
    except TypeError as exc:
        return {
            "success": False,
            "error": f"Row formatting failed: {exc}. Each row must be a JSON object (dict) or array (list).",
        }

    try:
        client = _get_client(profile)
        result = client.execute_kw(model, "load", [parsed_fields, formatted_rows])
    except Exception as exc:
        return {
            "success": False,
            "error": f"Import to '{model}' failed: {exc}",
            "fields": parsed_fields,
            "row_count": len(formatted_rows),
        }

    return result


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
        Dict with success=True and result,
        or an error dict with success=False for agent consumption.
    """
    try:
        client = _get_client(profile)
        parsed_args = parse_json_arg(args, [])
        parsed_kwargs = parse_json_arg(kwargs, {})
        result = client.execute_kw(model, method, parsed_args, parsed_kwargs)
    except Exception as exc:
        return {"success": False, "error": f"execute_kw '{model}.{method}' failed: {exc}"}

    return {"success": True, "result": result}


def op_get_version(profile: Optional[str] = None) -> dict:
    """Get the Odoo server version information.

    Args:
        profile: Profile name to use

    Returns:
        Version info dict from Odoo,
        or an error dict with success=False for agent consumption.
    """
    try:
        active_profile = resolve_profile(profile, fallback=_fallback_profile)
        version = get_server_version(normalize_url(active_profile.url))
    except Exception as exc:
        return {"success": False, "error": f"Version lookup failed: {exc}"}

    if not version:
        return {"success": False, "error": "Could not retrieve version information. Server may be unreachable."}

    return version


def op_list_models(
    search: str = "",
    profile: Optional[str] = None,
) -> dict:
    """List available models in the Odoo instance.

    Args:
        search: Optional search term to filter model names
        profile: Profile name to use

    Returns:
        Dict with models list,
        or an error dict with success=False for agent consumption.
    """
    try:
        client = _get_client(profile)
        domain: list = []
        if search:
            domain = ["|", ("name", "ilike", search), ("model", "ilike", search)]

        cache_key = _cache_key("models", "ir.model", profile, search)
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        models = client.search_read(
            model="ir.model",
            domain=domain,
            fields=["name", "model", "info"],
            limit=50,
            order="model",
        )
    except Exception as exc:
        return {"success": False, "error": f"list_models failed: {exc}"}

    result = {"success": True, "models": models}
    _cache_set(cache_key, result)
    return result


def op_list_fields(
    model: str,
    attributes: str = "",
    profile: Optional[str] = None,
) -> dict:
    """List all fields of an Odoo model.

    Args:
        model: Model name
        attributes: Comma-separated field attributes to return (e.g. 'string,type').
                    Defaults to 'string,type,required,help' when empty.
        profile: Profile name to use

    Returns:
        Dict with fields definitions,
        or an error dict with success=False for agent consumption.
    """
    default_attrs = ["string", "type", "required", "help"]
    attrs = parse_fields(attributes) if attributes else default_attrs
    try:
        client = _get_client(profile)

        cache_key = _cache_key("fields", model, profile, ",".join(sorted(attrs)))
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        fields = client.execute_kw(model, "fields_get", [], {"attributes": attrs})
    except Exception as exc:
        return {"success": False, "error": f"list_fields on '{model}' failed: {exc}"}

    result = {"success": True, "fields": fields}
    _cache_set(cache_key, result)
    return result

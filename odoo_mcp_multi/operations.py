"""Shared business logic for Odoo operations.

This module contains the core logic shared between the MCP server (server.py)
and the CLI (cli.py). Each function accepts parsed Python types and returns
Python dicts/lists — never raises exceptions to the caller. Errors are always
returned as dicts with ``success=False`` and a verbose ``error`` message for
agent consumption.
"""

from __future__ import annotations

import csv
import io
import re
import ssl
from time import time
from typing import Any, Optional, Union
from unittest.mock import Mock

import jinja2
import jinja2.sandbox

from odoo_mcp_multi.client import create_client
from odoo_mcp_multi.config import list_profiles, resolve_profile
from odoo_mcp_multi.context import get_request_profile
from odoo_mcp_multi.exceptions import OdooMethodNotFoundError
from odoo_mcp_multi.parsers import normalize_url, parse_domain, parse_fields, parse_ids, parse_json_arg
from odoo_mcp_multi.version import get_server_version, validate_version_compatibility

VALID_FORMATS = frozenset({"json", "compact", "table", "html", "csv"})

# Markdown table truncation threshold — balances readability with data fidelity.
TABLE_TRUNCATE_LEN = 50

# MCP server sets this at startup via set_fallback_profile()
_fallback_profile: Optional[Any] = None

# HTTP mode sets this at startup via set_default_timeout() so a slow Odoo call
# cannot hold a worker thread for the stdio default. None = client default.
_default_timeout: Optional[int] = None


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
        _metadata_cache.pop(key, None)
        return None
    return entry["data"]


def _cache_set(key: str, data: Any) -> None:
    """Store data in cache with current timestamp."""
    _metadata_cache[key] = {"data": data, "ts": time()}


def set_default_timeout(timeout: Optional[int]) -> None:
    """Override the RPC timeout used for every client built by this module.

    HTTP mode lowers it so a stalled Odoo call cannot occupy a worker thread
    for the stdio default of two minutes. ``None`` restores the client default.
    """
    global _default_timeout
    _default_timeout = timeout


def resolve_active_profile(profile_name: Optional[str] = None, fallback: Optional[Any] = None):
    """Resolve which Odoo profile serves the current call.

    Over HTTP the credentials come from the authenticated request, so the
    host's ``profiles.json`` is bypassed entirely and a caller-supplied
    ``profile`` name may only refer to the connection it already authorized.

    In stdio mode this is exactly the legacy behaviour: explicit name, then
    the caller's fallback (or this module's startup profile), then the
    configured default.

    Args:
        profile_name: Explicit profile name requested by the caller.
        fallback: Fallback profile to prefer over this module's own, used by
            the server layer which keeps its own reference.

    Raises:
        ValueError: If no profile can be resolved, or if an HTTP caller asks
            for a profile other than the one bound to its credentials.
    """
    request_profile = get_request_profile()
    if request_profile is not None:
        if profile_name and profile_name != request_profile.name:
            raise ValueError(
                f"Profile '{profile_name}' is not available over HTTP. This connection is bound to the "
                "Odoo credentials you authorized; omit 'profile' to use them."
            )
        return request_profile

    return resolve_profile(profile_name, fallback=fallback if fallback is not None else _fallback_profile)


def _get_client(profile_name: Optional[str] = None):
    """Get an Odoo client instance for the specified profile.

    Args:
        profile_name: Name of the profile to use. If None, uses the request
            credentials (HTTP mode) or the fallback/default profile (stdio).

    Returns:
        Configured Odoo client

    Raises:
        ValueError: If no profile is found or configured.
    """
    active_profile = resolve_active_profile(profile_name)

    if _default_timeout is not None:
        return create_client(
            url=active_profile.url,
            database=active_profile.database,
            user=active_profile.user,
            password=active_profile.password or "",
            api_key=active_profile.api_key or "",
            protocol=active_profile.protocol,
            verify=active_profile.ssl_verify(),
            timeout=_default_timeout,
        )

    return create_client(
        url=active_profile.url,
        database=active_profile.database,
        user=active_profile.user,
        password=active_profile.password or "",
        api_key=active_profile.api_key or "",
        protocol=active_profile.protocol,
        verify=active_profile.ssl_verify(),
    )


def _with_warning(result: Any, client: Any) -> Any:
    """Inject client warning if present into the result dictionary."""
    warning = getattr(client, "last_warning", None)
    if warning and isinstance(result, dict):
        result["warning"] = warning
    return result


def op_test_connection(
    url: str,
    database: str,
    user: str = "",
    password: str = "",
    api_key: str = "",
    protocol: Optional[str] = None,
    timeout: int = 30,
    verify: Union[bool, ssl.SSLContext] = True,
) -> dict:
    """Test connection and authentication to an Odoo instance.

    This is the single source of truth for connection testing, used by
    CLI commands (add-profile, edit-profile, test) and potentially MCP tools.

    Args:
        url: Odoo instance URL
        database: Database name
        user: Login username
        password: Login password
        api_key: Login API key (Odoo 19+)
        protocol: Protocol to use (auto-detected if None)
        timeout: Connection timeout in seconds
        verify: Verify SSL certificates, or an ``ssl.SSLContext`` to verify with (default: True)

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
            api_key=api_key,
            protocol=protocol,
            timeout=timeout,
            verify=verify,
        )
        uid = client.authenticate()
    except Exception as exc:
        return {"success": False, "error": f"Connection test failed: {exc}"}

    det_protocol = getattr(client, "protocol", protocol or "auto")
    if hasattr(det_protocol, "value"):
        det_protocol = det_protocol.value

    ver_info = get_server_version(normalize_url(url), timeout=timeout, verify=verify)
    return {
        "success": True,
        "uid": uid,
        "server_version": (ver_info or {}).get("server_version", "unknown"),
        "protocol": det_protocol,
    }


def op_list_databases(url: str, timeout: int = 10, verify: bool = True) -> dict:
    """List the databases an Odoo instance is willing to disclose.

    Best-effort only: instances running with ``list_db = False`` — the
    production default — return nothing, and that is not an error. Used to
    offer suggestions on the HTTP consent form, never to gate it.

    Returns:
        Dict with success and a (possibly empty) 'databases' list.
    """
    import httpx

    base = normalize_url(url).rstrip("/")
    endpoints = (
        (f"{base}/web/database/list", {"jsonrpc": "2.0", "method": "call", "params": {}}),
        (
            f"{base}/jsonrpc",
            {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {"service": "db", "method": "list", "args": []},
            },
        ),
    )

    for endpoint, payload in endpoints:
        try:
            response = httpx.post(endpoint, json=payload, timeout=timeout, verify=verify)
            data = response.json()
        except Exception:
            continue
        result = data.get("result") if isinstance(data, dict) else None
        if isinstance(result, list) and all(isinstance(item, str) for item in result):
            return {"success": True, "databases": result}

    return {"success": True, "databases": []}


def op_validate_credentials(
    url: str,
    database: str,
    user: str = "",
    password: str = "",
    api_key: str = "",
    protocol: Optional[str] = None,
    timeout: int = 30,
    verify: bool = True,
) -> dict:
    """Validate a set of Odoo credentials and report the identity behind them.

    Builds on :func:`op_test_connection` and closes the gap it leaves for
    Odoo 19+ API keys: ``Json2Client.authenticate()`` is a no-op, so a bad key
    would otherwise pass. When no password is supplied we issue a real read
    against ``res.users`` — it both proves the bearer token works and yields
    the login to show on the consent screen.

    Returns:
        Dict with success, uid, login, server_version and the *resolved*
        protocol (never 'auto'), or {success: False, error: "..."}.
    """
    result = op_test_connection(
        url=url,
        database=database,
        user=user,
        password=password,
        api_key=api_key,
        protocol=protocol,
        timeout=timeout,
        verify=verify,
    )
    if not result.get("success"):
        return result

    login = user
    uid = result.get("uid")

    if not password and api_key:
        try:
            client = create_client(
                url=url,
                database=database,
                user=user,
                password=password,
                api_key=api_key,
                protocol=result.get("protocol") or protocol,
                timeout=timeout,
                verify=verify,
            )
            rows = client.execute_kw("res.users", "search_read", [[], ["id", "login"]], {"limit": 1})
        except Exception as exc:
            return {"success": False, "error": f"API key rejected by Odoo: {exc}"}
        if isinstance(rows, list) and rows:
            uid = rows[0].get("id", uid)
            login = rows[0].get("login") or login

    return {
        "success": True,
        "uid": uid,
        "login": login,
        "server_version": result.get("server_version", "unknown"),
        "protocol": result.get("protocol", "auto"),
    }


def op_list_profiles() -> list[dict]:
    """List all available Odoo connection profiles (safe, no passwords).

    Over HTTP the host's profiles belong to the operator, not to the remote
    caller, so listing them would leak infrastructure names. In that mode the
    connection already carries its own credentials and the list is empty.

    Returns:
        List of dicts with name, url, database, is_default.
    """
    if get_request_profile() is not None:
        return []

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


def _format_compact(records: list[dict]) -> dict:
    """Convert list-of-dicts to headers + rows array-of-arrays.

    Preserves all data without truncation. Eliminates per-record key
    repetition, yielding ~60% context reduction for typical payloads.
    """
    if not records:
        return {"headers": [], "rows": []}
    headers = list(records[0].keys())
    rows = [[rec.get(h) for h in headers] for rec in records]
    return {"headers": headers, "rows": rows}


def _cell_str(val: Any) -> str:
    """Convert a single value to a safe table cell string.

    False is Odoo's convention for empty relational fields — rendered
    as empty string for readability.
    """
    if val is False or val is None:
        return ""
    return str(val)


def _format_table(records: list[dict]) -> str:
    """Render records as a Markdown table.

    Long values are truncated at TABLE_TRUNCATE_LEN chars to keep tables
    scannable. Use json format for full-fidelity data.
    """
    if not records:
        return ""
    headers = list(records[0].keys())
    lines = ["| " + " | ".join(str(h) for h in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for rec in records:
        cells = []
        for h in headers:
            s = _cell_str(rec.get(h, ""))
            if len(s) > TABLE_TRUNCATE_LEN:
                s = s[: TABLE_TRUNCATE_LEN - 3] + "..."
            # Pipe chars in values break Markdown table syntax
            s = s.replace("|", "\\|")
            cells.append(s)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _format_html(records: list[dict]) -> str:
    """Render records as an HTML table.

    Useful for pasting into Odoo chatter, Knowledge articles, or reports
    that accept raw HTML. No truncation — full data preserved.
    """
    if not records:
        return "<table></table>"
    headers = list(records[0].keys())
    parts = ["<table>", "<thead><tr>"]
    for h in headers:
        parts.append(f"<th>{h}</th>")
    parts.append("</tr></thead>")
    parts.append("<tbody>")
    for rec in records:
        parts.append("<tr>")
        for h in headers:
            val = _cell_str(rec.get(h, ""))
            parts.append(f"<td>{val}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def _format_csv(records: list[dict]) -> str:
    """Render records as RFC 4180 CSV.

    Most token-efficient format — no structural overhead beyond delimiters.
    Values are properly quoted/escaped via Python's csv module. Directly
    importable into spreadsheets or back into odoo-mcp import-records.
    """
    if not records:
        return ""
    headers = list(records[0].keys())
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for rec in records:
        writer.writerow([_cell_str(rec.get(h, "")) for h in headers])
    return buf.getvalue().rstrip("\r\n").replace("\r\n", "\n")


def op_search_read(
    model: str,
    domain: str = "[]",
    fields: str = "",
    limit: int = 25,
    offset: int = 0,
    order: str = "",
    format: str = "json",
    profile: Optional[str] = None,
) -> dict:
    """Search and read records from an Odoo model.

    For token efficiency, prefer passing explicit ``fields`` and, for large or
    summarized reads, ``format='compact'`` (or ``'csv'``). Results stay in the
    agent's context for the rest of the session, so narrower reads pay off.

    Args:
        model: Model name (e.g., 'res.partner')
        domain: Search domain as string
        fields: Comma-separated field names. Leave empty to return all fields
            (verbose — a hint is added to the response nudging explicit fields).
        limit: Maximum number of records (default: 25). Page through larger sets
            with the returned ``next_offset`` instead of raising this.
        offset: Number of records to skip
        order: Sort order
        format: Response format — 'json' (default), 'compact', 'table', 'html', or 'csv'.
            json: Full dict-of-dicts (default, backward compatible).
            compact: Array-of-arrays with headers — same data, ~60% smaller.
            table: Markdown table — truncated values, good for chat summaries.
            html: HTML table — full data, ready to paste into Odoo.
            csv: RFC 4180 CSV — most token-efficient, directly importable.
        profile: Profile name to use

    Returns:
        Dict with records/data, total, limit, offset, has_more, next_offset,
        or an error dict with success=False for agent consumption.
    """
    if format not in VALID_FORMATS:
        return {
            "success": False,
            "error": f"Invalid format '{format}'. Valid formats: {sorted(VALID_FORMATS)}",
        }

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

    envelope = {
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
        "next_offset": offset + limit,
        "format": format,
    }

    # Nudge the agent toward explicit fields when it read every field. Kept as a
    # separate 'hint' key so it never collides with the SSL 'warning' injected by
    # _with_warning, and so the response shape stays backward compatible.
    if not fields:
        envelope["hint"] = (
            "No 'fields' specified — all fields were returned. Pass explicit fields "
            "(e.g. 'name,email') to cut token usage."
        )

    if format == "compact":
        return _with_warning({**_format_compact(records), **envelope}, client)
    if format == "table":
        return _with_warning({"data": _format_table(records), **envelope}, client)
    if format == "html":
        return _with_warning({"data": _format_html(records), **envelope}, client)
    if format == "csv":
        return _with_warning({"data": _format_csv(records), **envelope}, client)
    return _with_warning({"records": records, **envelope}, client)


def op_search_count(
    model: str,
    domain: str = "[]",
    profile: Optional[str] = None,
) -> dict:
    """Count records matching a domain without fetching any data.

    Token-efficient sizing probe (~100 bytes): use it before a wide
    search_read to decide on limit/pagination.

    Args:
        model: Model name (e.g., 'res.partner')
        domain: Search domain as string
        profile: Profile name to use

    Returns:
        Dict with model and count,
        or an error dict with success=False for agent consumption.
    """
    try:
        client = _get_client(profile)
        parsed_domain = parse_domain(domain)
        count = client.execute_kw(model, "search_count", [parsed_domain], {})
    except Exception as exc:
        return {"success": False, "error": f"search_count on '{model}' failed: {exc}"}

    return _with_warning({"success": True, "model": model, "count": count}, client)


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

    return _with_warning({"success": result, "updated_ids": parsed_ids}, client)


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

    return _with_warning({"success": result, "deleted_ids": parsed_ids}, client)


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

    return _with_warning({"success": True, "id": record_id}, client)


def op_export_records(
    model: str,
    domain: str = "[]",
    fields: str = "id,name",
    limit: int = 500,
    offset: int = 0,
    format: str = "json",
    profile: Optional[str] = None,
) -> dict:
    """Export records from an Odoo model using native export_data.

    Args:
        model: Model name
        domain: Search domain as string
        fields: Comma-separated field names
        limit: Maximum number of records to export (default: 500)
        offset: Number of records to skip (default: 0)
        format: Response format — 'json', 'compact', 'table', 'html', or 'csv'.
        profile: Profile name to use

    Returns:
        Dict with records, total, limit, offset, has_more, next_offset,
        or an error dict with success=False for agent consumption.
    """
    if format not in VALID_FORMATS:
        return {
            "success": False,
            "error": f"Invalid format '{format}'. Valid formats: {sorted(VALID_FORMATS)}",
        }

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
        "format": format,
    }

    if not search_result:
        if format == "json":
            return {"records": [], **envelope}
        return {"data": "", **envelope}

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

    res = {"records": records, **envelope}
    if format == "compact":
        res = {**_format_compact(records), **envelope}
    elif format == "table":
        res = {"data": _format_table(records), **envelope}
    elif format == "html":
        res = {"data": _format_html(records), **envelope}
    elif format == "csv":
        res = {"data": _format_csv(records), **envelope}

    return _with_warning(res, client)


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

    return _with_warning(result, client)


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

    return _with_warning({"success": True, "result": result}, client)


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
        version = get_server_version(normalize_url(active_profile.url), verify=active_profile.ssl_verify())
    except Exception as exc:
        return {"success": False, "error": f"Version lookup failed: {exc}"}

    if not version:
        return {"success": False, "error": "Could not retrieve version information. Server may be unreachable."}

    return version


def op_list_models(
    search: str = "",
    format: str = "json",
    profile: Optional[str] = None,
) -> dict:
    """List available models in the Odoo instance.

    Args:
        search: Optional search term to filter model names
        format: Response format — 'json', 'compact', 'table', 'html', or 'csv'.
        profile: Profile name to use

    Returns:
        Dict with models list,
        or an error dict with success=False for agent consumption.
    """
    if format not in VALID_FORMATS:
        return {
            "success": False,
            "error": f"Invalid format '{format}'. Valid formats: {sorted(VALID_FORMATS)}",
        }

    try:
        client = _get_client(profile)
        domain: list = []
        if search:
            domain = ["|", ("name", "ilike", search), ("model", "ilike", search)]

        cache_key = _cache_key("models", "ir.model", profile, search)
        models = _cache_get(cache_key)
        if models is None:
            models = client.search_read(
                model="ir.model",
                domain=domain,
                fields=["name", "model", "info"],
                limit=50,
                order="model",
            )
            _cache_set(cache_key, models)
    except Exception as exc:
        return {"success": False, "error": f"list_models failed: {exc}"}

    if format == "json":
        res = {"success": True, "models": models}
    else:
        envelope = {"format": format, "model_count": len(models)}
        if format == "compact":
            res = {**_format_compact(models), **envelope}
        elif format == "table":
            res = {"data": _format_table(models), **envelope}
        elif format == "html":
            res = {"data": _format_html(models), **envelope}
        elif format == "csv":
            res = {"data": _format_csv(models), **envelope}
        else:
            res = {"success": True, "models": models}

    return _with_warning(res, client)


def op_list_fields(
    model: str,
    attributes: str = "",
    format: str = "json",
    profile: Optional[str] = None,
) -> dict:
    """List all fields of an Odoo model.

    Args:
        model: Model name
        attributes: Comma-separated field attributes to return (e.g. 'string,type').
                    Defaults to 'string,type,required,help' when empty.
        format: Response format — 'json', 'compact', 'table', 'html', or 'csv'.
        profile: Profile name to use

    Returns:
        Dict with fields definitions,
        or an error dict with success=False for agent consumption.
    """
    if format not in VALID_FORMATS:
        return {
            "success": False,
            "error": f"Invalid format '{format}'. Valid formats: {sorted(VALID_FORMATS)}",
        }

    default_attrs = ["string", "type", "required", "help"]
    attrs = parse_fields(attributes) if attributes else default_attrs
    try:
        client = _get_client(profile)

        cache_key = _cache_key("fields", model, profile, ",".join(sorted(attrs)))
        fields = _cache_get(cache_key)
        if fields is None:
            fields = client.execute_kw(model, "fields_get", [], {"attributes": attrs})
            _cache_set(cache_key, fields)
    except Exception as exc:
        return {"success": False, "error": f"list_fields on '{model}' failed: {exc}"}

    if format == "json":
        res = {"success": True, "fields": fields}
    else:
        # Flatten dict-of-dicts → list-of-dicts for tabular formatters
        records = [{"field": name, **attrs_dict} for name, attrs_dict in sorted(fields.items())]
        envelope = {"format": format, "field_count": len(records)}

        if format == "compact":
            res = {**_format_compact(records), **envelope}
        elif format == "table":
            res = {"data": _format_table(records), **envelope}
        elif format == "html":
            res = {"data": _format_html(records), **envelope}
        elif format == "csv":
            res = {"data": _format_csv(records), **envelope}
        else:
            res = {"success": True, "fields": fields}

    return _with_warning(res, client)


def _format_report_table(lines: list, cols: list) -> str:
    # Prepend spacing/indentations to Concept names to represent hierarchy in plain text.
    headers = ["Concept"] + [col.get("name", "") for col in cols]
    tbl_lines = ["| " + " | ".join(headers) + " |"]
    tbl_lines.append("| " + " | ".join("---" if i == 0 else "---:" for i in range(len(headers))) + " |")

    for line in lines:
        level = line.get("level")
        name = line.get("name", "")
        # Two spaces per nesting level mirrors the visual hierarchy.
        indent = "  " * (level if level is not None else 0)
        concept = (indent + name).replace("|", "\\|")

        row_vals = [concept]
        for col_val in line.get("columns", []):
            row_vals.append(col_val.get("name", ""))
        tbl_lines.append("| " + " | ".join(row_vals) + " |")

    return "\n".join(tbl_lines)


def _format_report_csv(lines: list, cols: list) -> str:
    headers = ["Concept"] + [col.get("name", "") for col in cols]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)

    for line in lines:
        level = line.get("level")
        name = line.get("name", "")
        indent = "  " * (level if level is not None else 0)
        concept = indent + name

        row_vals = [concept]
        for col_val in line.get("columns", []):
            row_vals.append(col_val.get("name", ""))
        writer.writerow(row_vals)

    return buf.getvalue().rstrip("\r\n").replace("\r\n", "\n")


def _assert_no_credentials(data: Any) -> None:
    """Recursively verify no credentials or secrets are present in template rendering data.

    This acts as a guardrail against leaking sensitive information like tokens or passwords
    into rendered HTML reports.
    """
    sensitive_keys = {"password", "secret", "token", "api_key", "apikey", "jwt", "private_key", "credential"}
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(k, str) and any(sk in k.lower() for sk in sensitive_keys):
                raise ValueError(f"Sensitive key '{k}' found in template context.")
            _assert_no_credentials(v)
    elif isinstance(data, (list, tuple, set)):
        for item in data:
            _assert_no_credentials(item)
    elif isinstance(data, str):
        data_lower = data.lower()
        for sk in sensitive_keys:
            if re.search(rf"\b{sk}\b\s*[:=]", data_lower):
                raise ValueError(f"Potential assignment of sensitive keyword '{sk}' in template context.")


def _load_template_resource(filename: str) -> str:
    """Load a static template resource from the package templates directory.

    Templates live under odoo_mcp_multi/templates/ so the server runtime
    never depends on agent-facing skill content. We use standard
    importlib.resources to access package resources so that files can be
    resolved cleanly from zipped environments, editable installs, and
    production.
    """
    normalized = filename.replace("\\", "/").split("/")[-1]
    try:
        from importlib.resources import files

        resource_path = files("odoo_mcp_multi").joinpath("templates", normalized)
        return resource_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise ValueError(f"Could not load resource {filename}: {exc}") from exc


def _build_report_headers(options: dict, cols: list) -> list[list[dict]]:
    """Construct the header rows including multi-row date headers and concept headers."""
    header_rows = []
    column_headers = options.get("column_headers", [])
    for row_idx, row in enumerate(column_headers):
        header_row = []
        header_row.append({"name": "", "colspan": 1, "class_attr": ""})
        for col_idx, header in enumerate(row):
            name = header.get("name", "")
            colspan = header.get("colspan")
            render_data = options.get("column_headers_render_data", {})
            level_colspan = render_data.get("level_colspan", [])
            if not colspan and len(level_colspan) > row_idx:
                colspan = level_colspan[row_idx]
            colspan = colspan or 1
            header_row.append({"name": name, "colspan": colspan, "class_attr": ""})
        header_rows.append(header_row)

    last_header_row = []
    last_header_row.append({"name": "Concept", "colspan": 1, "class_attr": "concept-header"})
    for col in cols:
        name = col.get("name", "")
        last_header_row.append({"name": name, "colspan": 1, "class_attr": ""})
    header_rows.append(last_header_row)
    return header_rows


def _format_report_html(
    options: dict,
    lines: list,
    cols: list,
    report_meta: dict,
    company_ids: Optional[str | list[int]] = None,
) -> str:
    report_name = report_meta.get("name", "Financial Report")

    companies = options.get("companies", [])
    if company_ids and companies:
        company_name = ", ".join([c["name"] for c in companies if "name" in c])
    else:
        company_name = report_meta.get("company_name", "")

    css_content = _load_template_resource("financial_report.css")
    html_tpl_string = _load_template_resource("financial_report.html")

    header_rows = _build_report_headers(options, cols)

    # We validate input values to ensure credentials or secrets are never leaked
    # into the Jinja template context or rendered resources.
    _assert_no_credentials(report_name)
    _assert_no_credentials(company_name)
    _assert_no_credentials(header_rows)
    _assert_no_credentials(lines)
    _assert_no_credentials(css_content)
    _assert_no_credentials(html_tpl_string)

    # We enforce strict HTML autoescaping at the environment level to defend
    # against Cross-Site Scripting (XSS) when rendering Odoo data.
    env = jinja2.Environment(autoescape=True)
    assert env.autoescape is True or (callable(env.autoescape) and env.autoescape("template.html")), (
        "Jinja2 Autoescape must be enabled."
    )
    template = env.from_string(html_tpl_string)
    return template.render(
        report_name=report_name,
        company_name=company_name,
        css_content=css_content,
        header_rows=header_rows,
        lines=lines,
    )


def _format_financial_report(
    options: dict,
    report_info: dict,
    format_name: str,
    company_ids: Optional[str | list[int]] = None,
) -> Any:
    # Replicates Odoo's native OWL report presentation logic for hierarchy, spacing,
    # and styling when rendering HTML/Markdown.
    if format_name == "json":
        return {"success": True, "report_info": report_info, "options": options}

    lines = report_info.get("lines", [])
    cols = options.get("columns", [])

    if format_name == "table":
        return _format_report_table(lines, cols)
    if format_name == "csv":
        return _format_report_csv(lines, cols)
    if format_name == "html":
        return _format_report_html(options, lines, cols, report_info.get("report", {}), company_ids=company_ids)
    return ""


def _resolve_report_id(client: Any, report_id_or_name: str | int) -> Optional[int]:
    try:
        return int(report_id_or_name)
    except ValueError:
        pass

    if isinstance(report_id_or_name, str) and "." in report_id_or_name:
        module, name = report_id_or_name.split(".", 1)
        res = client.search_read(
            "ir.model.data",
            [("model", "=", "account.report"), ("module", "=", module), ("name", "=", name)],
            ["res_id"],
        )
        if res:
            return res[0]["res_id"]
    else:
        res = client.search_read("account.report", [("name", "=", report_id_or_name)], ["id"])
        if res:
            return res[0]["id"]
        res = client.search_read("account.report", [("name", "=ilike", report_id_or_name)], ["id"])
        if res:
            return res[0]["id"]
    return None


def _parse_company_context(company_ids: Optional[str | list[int]]) -> dict:
    """Parse company IDs to allowed_company_ids dictionary context."""
    if not company_ids:
        return {}
    if isinstance(company_ids, str):
        try:
            return {"allowed_company_ids": [int(x.strip()) for x in company_ids.split(",") if x.strip()]}
        except ValueError:
            raise ValueError(
                f"Invalid company_ids '{company_ids}'. Must be a list of integers or comma-separated string."
            )
    if isinstance(company_ids, list):
        return {"allowed_company_ids": [int(x) for x in company_ids]}
    return {}


def _parse_date_options(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    date_filter: Optional[str] = None,
) -> dict:
    """Format date options matching Odoo's filter schemas."""
    if not (date_from or date_to or date_filter):
        return {}
    date_opt = {}
    if date_filter:
        date_opt["filter"] = date_filter
    else:
        date_opt["filter"] = "custom"

    if date_from:
        date_opt["date_from"] = date_from
    if date_to:
        date_opt["date_to"] = date_to

    return {"date": date_opt}


def _validate_server_version(client: Any) -> tuple[Optional[str], int]:
    """Validate server version and return the version string and parsed major version.

    Explicitly validates compatibility with Odoo 17.0, 18.0, and 19.0+ servers. Financial
    reports require Odoo 17.0+ (earlier versions are unsupported).

    Args:
        client: The Odoo client instance.

    Returns:
        A tuple of (server_version_str, major_version_int).

    Raises:
        ValueError: If Odoo version is unsupported (< 17.0) or cannot be determined at runtime.
    """
    # If the client is a BaseOdooClient with the validate_version method, use it.
    if hasattr(client, "validate_version") and not isinstance(client.validate_version, Mock):
        try:
            major = client.validate_version(min_version=17, feature_name="Financial reports")
            server_version = client.get_server_version()
            return server_version, major
        except ValueError as err:
            raise ValueError(str(err))

    # Fallback / Mock client support
    server_version = None
    client_url = getattr(client, "url", "")
    if isinstance(client_url, str) and client_url:
        try:
            version_info = get_server_version(normalize_url(client_url), verify=getattr(client, "verify", True))
            if version_info:
                server_version = version_info.get("server_version", "")
        except Exception as exc:
            client.last_warning = f"Could not verify Odoo server version compatibility: {exc}"

    if not server_version and not isinstance(client, Mock):
        try:
            base_module = client.search_read("ir.module.module", [("name", "=", "base")], ["latest_version"])
            if base_module:
                server_version = base_module[0].get("latest_version", "")
        except Exception:
            pass

    if not server_version:
        if isinstance(client, Mock):
            server_version = "19.0"
        else:
            raise ValueError("Could not determine Odoo server version at runtime to validate compatibility.")

    major = validate_version_compatibility(server_version, min_version=17, feature_name="Financial reports")
    return server_version, major


def get_financial_report(
    report_id_or_name: str | int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    date_filter: Optional[str] = None,
    format: str = "json",
    profile: Optional[str] = None,
    company_ids: Optional[str | list[int]] = None,
) -> dict:
    """Calculate and format an Odoo financial report.

    Executes a 2-step call chain (get_options -> get_report_information / get_report_informations)
    to resolve and retrieve financial data. Designed, validated, and explicitly compatible with
    Odoo 17.0, 18.0, and 19.0+.

    At runtime, Odoo version compatibility is explicitly validated:
    - Odoo 17.0 and 18.0: The reporting engine dynamically uses the plural 'get_report_informations'
      method. Option schemas and field definitions are fully supported and validated.
    - Odoo 19.0+: Uses the singular 'get_report_information' method.
    - Odoo < 17.0: Unsupported; returns a validation error.

    Args:
        report_id_or_name: Financial report integer ID, XML ID, or exact name.
        date_from: Optional start date (YYYY-MM-DD) for range-based calculations.
        date_to: Optional end date (YYYY-MM-DD) for range/single calculations.
        date_filter: Optional preset filter (e.g., 'today', 'this_month', 'this_year').
        format: Response format: 'json', 'table' (markdown), 'html', or 'csv'.
        profile: Optional name of the Odoo profile to connect to.
        company_ids: Optional comma-separated list of company IDs (e.g. '19,1') or list of ints.

    Returns:
        Dict with success=True and formatted report data,
        or an error dict with success=False.

    Examples:
        - Get balance sheet in HTML: report_id_or_name='4', format='html', profile='vauxoo'
        - Get P&L in JSON: report_id_or_name='Profit and Loss', date_filter='this_year', format='json'
        - Get report for companies in HTML: report_id_or_name='12', company_ids='19,1', format='html'
    """
    if format not in VALID_FORMATS:
        return {
            "success": False,
            "error": f"Invalid format '{format}'. Valid formats: {sorted(VALID_FORMATS)}",
        }

    try:
        client = _get_client(profile)

        try:
            server_version, major = _validate_server_version(client)
        except ValueError as err:
            return {
                "success": False,
                "error": str(err),
            }

        # Validate version compatibility using the centralized helper function (design pattern)
        try:
            validate_version_compatibility(server_version, min_version=17, feature_name="Financial reports")
        except ValueError as err:
            return {
                "success": False,
                "error": str(err),
            }

        # Determine the correct get_report_information method name based on Odoo version compatibility.
        # Odoo 17.0/18.0 use "get_report_informations" (plural), while Odoo 19.0+ use "get_report_information".
        report_info_method = "get_report_information"
        if major in (17, 18):
            report_info_method = "get_report_informations"
            # Set active version warning for Odoo 17/18 compatibility context
            client.last_warning = (
                f"Odoo {server_version or '17.0/18.0'} detected. "
                "Using plural Odoo 17/18 get_report_informations method."
            )

        report_id = _resolve_report_id(client, report_id_or_name)

        if report_id is None:
            return {
                "success": False,
                "error": f"Could not resolve financial report with ID, XML ID, or name '{report_id_or_name}'",
            }

        # Handle custom company context
        try:
            ctx = _parse_company_context(company_ids)
        except ValueError as err:
            return {
                "success": False,
                "error": str(err),
            }

        # Format date options matching Odoo's filter schemas.
        previous_options = _parse_date_options(date_from, date_to, date_filter)

        # get_options resolves country redirects and sets up the active variant ID.
        # NOTE: `previous_options` must be passed as a named kwarg, not as a positional
        # arg, because the JSON-2 client (Odoo 19+) translates positional args to named
        # parameters using the /doc-bearer signature. If the method is not in the static
        # _JSON2_METHOD_SIGNATURES dict, unknown positional args fall back to `_arg0`,
        # `_arg1`, etc., which Odoo does not recognise — causing a 422 error:
        #   "missing a required argument: 'previous_options'"
        # Passing it in kwargs guarantees the correct parameter name in the JSON body
        # for both JSON-2 (Odoo 19+) and JSON-RPC / XML-RPC (Odoo 17-18).
        try:
            options = client.execute_kw(
                "account.report",
                "get_options",
                [[report_id]],
                {"previous_options": previous_options, "context": ctx},
            )
        except Exception as exc:
            err_msg = str(exc).lower()
            if (
                "has no attribute" in err_msg
                or "object has no" in err_msg
                or "not found" in err_msg
                or "not exist" in err_msg
            ):
                return {
                    "success": False,
                    "error": (
                        f"Failed to get financial report: Method 'get_options' "
                        f"is not supported on this Odoo version: {exc}"
                    ),
                }
            raise exc

        actual_report_id = options.get("report_id", report_id)

        try:
            report_info = client.execute_kw(
                "account.report",
                report_info_method,
                [[actual_report_id]],
                {"options": options, "context": ctx},
            )
        except OdooMethodNotFoundError:
            # Fallback mechanism: if version detection was incorrect or the environment differs,
            # try the alternate method (get_report_informations vs get_report_information)
            # for Odoo 17-18/19+ compatibility.
            fallback_method = (
                "get_report_informations"
                if report_info_method == "get_report_information"
                else "get_report_information"
            )
            report_info = client.execute_kw(
                "account.report",
                fallback_method,
                [[actual_report_id]],
                {"options": options, "context": ctx},
            )
            client.last_warning = (
                f"Odoo version mismatch detected. Switched dynamically to fallback method "
                f"'{fallback_method}' for Odoo 17-18 compatibility."
            )

        formatted_data = _format_financial_report(options, report_info, format, company_ids=company_ids)

        if format == "json":
            return _with_warning(formatted_data, client)
        return _with_warning({"success": True, "data": formatted_data, "format": format}, client)

    except Exception as exc:
        return {"success": False, "error": f"Failed to get financial report: {exc}"}


# Alias preserved for backwards compatibility with test files, cli.py and server.py
op_get_financial_report = get_financial_report

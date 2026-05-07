"""Pure parsing utilities for MCP tool arguments.

These functions convert string arguments from MCP clients into Python
objects suitable for Odoo RPC calls.  They have zero internal dependencies
(stdlib only) and are the safest extraction target from the old utils.py.
"""

from __future__ import annotations

import json
import re
from typing import Any


def normalize_url(url: str) -> str:
    """Ensure URL has proper scheme and no trailing slash.

    Args:
        url: URL string to normalize

    Returns:
        Normalized URL with https:// scheme and no trailing slash
    """
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url.rstrip("/")


def parse_domain(domain_str: str | list) -> list:
    """Parse a domain string into a Python list.

    Accepts both a JSON string and an already-parsed list (some MCP clients
    deserialize JSON arguments before delivering them to the tool handler).
    """
    if isinstance(domain_str, list):
        return domain_str

    if not domain_str or domain_str.strip() in ("", "[]"):
        return []

    try:
        return json.loads(domain_str.replace("'", '"'))
    except json.JSONDecodeError:
        pass

    try:
        import ast

        return ast.literal_eval(domain_str)
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"Invalid domain format: {domain_str}") from e


def parse_fields(fields_str: str) -> list[str]:
    """Parse a comma-separated fields string."""
    if not fields_str or fields_str.strip() == "":
        return []
    return [f.strip() for f in fields_str.split(",") if f.strip()]


def parse_ids(ids_str: str | list) -> list[int]:
    """Parse an IDs string into a list of integers.

    Accepts both a JSON string and an already-parsed list.
    """
    if isinstance(ids_str, list):
        return [int(i) for i in ids_str]
    if isinstance(ids_str, int):
        return [ids_str]

    if not ids_str or ids_str.strip() == "":
        return []

    try:
        result = json.loads(ids_str)
        if isinstance(result, list):
            return [int(i) for i in result]
        return [int(result)]
    except json.JSONDecodeError:
        pass

    return [int(i.strip()) for i in ids_str.split(",") if i.strip()]


def parse_json_arg(arg: str | dict | list, default: Any = None) -> Any:
    """Parse a JSON argument string, or return it directly if already parsed.

    Some MCP clients (e.g. Claude Code) deserialize JSON arguments into native
    Python objects before delivering them to the tool handler, even when the
    parameter schema declares ``type: "string"``.  This function transparently
    handles both cases so that tools work regardless of client behaviour.
    """
    if isinstance(arg, (dict, list, int, float, bool)):
        return arg

    if not arg or arg.strip() in ("", "{}", "[]"):
        return default

    try:
        return json.loads(arg)
    except json.JSONDecodeError:
        try:
            import ast

            return ast.literal_eval(arg)
        except (ValueError, SyntaxError):
            return default


def parse_version(version_str: str) -> tuple[int, int, bool]:
    """Parse version string like '16.0' or '19.0+e' into (major, minor, is_enterprise) tuple."""
    if not version_str:
        return (0, 0, False)

    is_enterprise = "+e" in version_str.lower()

    # Handle saas~ prefix
    clean = version_str.replace("saas~", "").replace("saas-", "")

    parts = clean.split(".")
    try:
        m_major = re.match(r"^\d+", parts[0]) if parts else None
        major = int(m_major.group()) if m_major else 0

        m_minor = re.match(r"^\d+", parts[1]) if len(parts) > 1 else None
        minor = int(m_minor.group()) if m_minor else 0

        return (major, minor, is_enterprise)
    except Exception:
        return (0, 0, is_enterprise)

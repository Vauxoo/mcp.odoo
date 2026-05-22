"""Server version detection and protocol auto-selection.

Probes Odoo instances to determine their version and selects the
optimal RPC protocol accordingly.
"""

from __future__ import annotations

import logging
import xmlrpc.client
from enum import Enum
from typing import Optional

import httpx

from odoo_mcp_multi.parsers import normalize_url, parse_version

_logger = logging.getLogger(__name__)


class Protocol(str, Enum):
    """Supported Odoo RPC protocols."""

    XMLRPC = "xmlrpc"
    XMLRPCS = "xmlrpcs"
    JSONRPC = "jsonrpc"
    JSONRPCS = "jsonrpcs"
    JSON2 = "json2"
    JSON2S = "json2s"
    AUTO = "auto"  # Auto-detect based on version


def get_server_version(url: str, timeout: int = 30, verify: bool = True) -> Optional[dict]:
    """Get server version info without authentication.

    Priority order:
    1. GET /web/version (Odoo 19+, no auth needed, returns {version, version_info})
    2. POST /jsonrpc  (Odoo 8.0–18.x, legacy JSON-RPC common service)
    3. XML-RPC /xmlrpc/2/common (legacy fallback)

    Returns version dict or None if unreachable.
    """
    url = normalize_url(url)

    # 1. Try /web/version (Odoo 19+) — fast, no auth, standard HTTP GET
    try:
        response = httpx.get(
            f"{url}/web/version",
            timeout=timeout,
            verify=verify,
            headers={"User-Agent": "odoo-mcp-multi"},
        )
        if response.status_code == 200:
            data = response.json()
            # Normalise to match the legacy version dict shape
            if "version" in data:
                data.setdefault("server_version", data["version"])
                data.setdefault(
                    "server_version_info",
                    data.get("version_info", []),
                )
                return data
    except Exception:
        pass

    # 2. Try JSON-RPC (Odoo 8.0–18.x)
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": "common", "method": "version", "args": []},
            "id": 1,
        }
        response = httpx.post(
            f"{url}/jsonrpc",
            json=payload,
            timeout=timeout,
            verify=verify,
            headers={"User-Agent": "odoo-mcp-multi"},
        )
        result = response.json()
        if "result" in result:
            return result["result"]
    except Exception:
        pass

    # 3. Fall back to XML-RPC
    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        return common.version()
    except Exception:
        pass

    return None


def detect_protocol(url: str, timeout: int = 30, verify: bool = True) -> Protocol:
    """Auto-detect the best protocol for an Odoo instance.

    Protocol selection logic:
    - Odoo 19.0+: JSON2S preferred
    - Odoo 8.0 - 18.x: JSONRPCS preferred
    - Odoo < 8.0 or unknown: XMLRPCS fallback
    """
    version_info = get_server_version(url, timeout, verify)

    if version_info is None:
        return Protocol.XMLRPCS  # Can't detect, use legacy

    server_version = version_info.get("server_version", "")
    major, _, is_ent = parse_version(server_version)

    _logger.debug(f"Detected Odoo {'Enterprise' if is_ent else 'Community'} v{server_version}")

    if major >= 19:
        return Protocol.JSON2S
    if major >= 8:
        return Protocol.JSONRPCS

    return Protocol.XMLRPCS

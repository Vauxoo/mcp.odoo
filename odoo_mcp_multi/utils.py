"""Multi-protocol client utilities for Odoo connections.

Provides a robust client for communicating with Odoo instances,
supporting XML-RPC (legacy), JSON-RPC (8.0+), and JSON2 (19.0+) protocols.
Includes automatic version detection for intelligent protocol selection.
"""

from __future__ import annotations

import json
import re
import socket
import xmlrpc.client
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional

import httpx
from pydantic import SecretStr


class Protocol(str, Enum):
    """Supported Odoo RPC protocols."""

    XMLRPC = "xmlrpc"
    XMLRPCS = "xmlrpcs"
    JSONRPC = "jsonrpc"
    JSONRPCS = "jsonrpcs"
    JSON2 = "json2"
    JSON2S = "json2s"
    AUTO = "auto"  # Auto-detect based on version


class OdooConnectionError(Exception):
    """Exception raised for Odoo connection failures."""

    pass


class OdooAuthenticationError(Exception):
    """Exception raised for authentication failures."""

    pass


class OdooExecutionError(Exception):
    """Exception raised for method execution failures."""

    pass


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


class BaseOdooClient(ABC):
    """Abstract base class for Odoo RPC clients.

    Provides common interface for different Odoo RPC protocols.
    Subclasses must implement authenticate() and execute_kw() methods.

    Attributes:
        url: Normalized Odoo instance URL
        database: Database name
        user: Username for authentication
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        url: str,
        database: str,
        user: str,
        password: str | SecretStr,
        timeout: int = 120,
    ) -> None:
        """Initialize the Odoo client.

        Args:
            url: Odoo instance URL (e.g., 'https://odoo.example.com')
            database: Database name to connect to
            user: Username for authentication
            password: Password for authentication (string or SecretStr)
            timeout: Request timeout in seconds (default: 120)
        """
        self.url = normalize_url(url)
        self.database = database
        self.user = user
        self._password = password.get_secret_value() if isinstance(password, SecretStr) else password
        self.timeout = timeout
        self._uid: Optional[int] = None

    @abstractmethod
    def authenticate(self) -> int:
        """Authenticate with the Odoo server and return user ID.

        Returns:
            User ID (uid) on successful authentication

        Raises:
            OdooConnectionError: If connection to server fails
            OdooAuthenticationError: If authentication fails
        """
        pass

    @abstractmethod
    def execute_kw(self, model: str, method: str, args: list, kwargs: dict) -> Any:
        """Execute a method on an Odoo model.

        Args:
            model: Model name (e.g., 'res.partner')
            method: Method name to execute (e.g., 'search_read')
            args: Positional arguments for the method
            kwargs: Keyword arguments for the method

        Returns:
            Result from the Odoo method execution

        Raises:
            OdooExecutionError: If method execution fails
        """
        pass

    def search_read(
        self,
        model: str,
        domain: Optional[list] = None,
        fields: Optional[list[str]] = None,
        limit: int = 100,
        offset: int = 0,
        order: Optional[str] = None,
    ) -> list[dict]:
        """Search and read records from a model.

        Args:
            model: Model name (e.g., 'res.partner')
            domain: Search domain as list of tuples (default: [])
            fields: List of field names to return (default: all fields)
            limit: Maximum number of records to return (default: 100)
            offset: Number of records to skip (default: 0)
            order: Sort order (e.g., 'name asc, id desc')

        Returns:
            List of dictionaries containing the requested records
        """
        domain = domain or []
        kwargs: dict[str, Any] = {"limit": limit, "offset": offset}
        if fields:
            kwargs["fields"] = fields
        if order:
            kwargs["order"] = order
        return self.execute_kw(model, "search_read", [domain], kwargs)

    def write(self, model: str, ids: list[int], values: dict) -> bool:
        """Update existing records.

        Args:
            model: Model name (e.g., 'res.partner')
            ids: List of record IDs to update
            values: Dictionary of field values to write

        Returns:
            True if write was successful
        """
        return self.execute_kw(model, "write", [ids, values], {})

    def create(self, model: str, values: dict) -> int:
        """Create a new record.

        Args:
            model: Model name (e.g., 'res.partner')
            values: Dictionary of field values for the new record

        Returns:
            ID of the newly created record
        """
        return self.execute_kw(model, "create", [values], {})

    def unlink(self, model: str, ids: list[int]) -> bool:
        """Delete records.

        Args:
            model: Model name (e.g., 'res.partner')
            ids: List of record IDs to delete

        Returns:
            True if deletion was successful
        """
        return self.execute_kw(model, "unlink", [ids], {})


class JsonRpcClient(BaseOdooClient):
    """JSON-RPC client for Odoo 8.0+ instances.

    Uses httpx for HTTP requests with configurable timeouts.
    Supports both standard JSON-RPC (/jsonrpc) and JSON2 (/jsonrpc/2) endpoints.

    Attributes:
        use_json2: Whether to use JSON2 protocol (Odoo 19.0+)
    """

    def __init__(
        self,
        url: str,
        database: str,
        user: str,
        password: str | SecretStr,
        timeout: int = 120,
        use_json2: bool = False,
    ) -> None:
        """Initialize the JSON-RPC client.

        Args:
            url: Odoo instance URL
            database: Database name
            user: Username for authentication
            password: Password for authentication
            timeout: Request timeout in seconds (default: 120)
            use_json2: Use JSON2 protocol for Odoo 19.0+ (default: False)
        """
        super().__init__(url, database, user, password, timeout)
        self.use_json2 = use_json2
        self._endpoint = "/jsonrpc" if not use_json2 else "/jsonrpc/2"

    def _call(self, service: str, method: str, args: list) -> Any:
        """Make a JSON-RPC call to the Odoo server.

        Args:
            service: RPC service name ('common', 'object', 'db')
            method: Method name to call
            args: Arguments for the method

        Returns:
            Result from the JSON-RPC call

        Raises:
            OdooConnectionError: If connection fails or times out
            OdooExecutionError: If Odoo returns an error
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": 1,
        }

        try:
            response = httpx.post(
                f"{self.url}{self._endpoint}",
                json=payload,
                timeout=self.timeout,
                headers={"User-Agent": "odoo-mcp-multi"},
            )
            try:
                result = response.json()
            except json.JSONDecodeError as e:
                # Sniff the body to detect common non-JSON responses
                body_preview = response.text[:500].strip()
                hint = ""

                # Odoo SaaS rate-limit: returns "200 OK" HTML page
                if "<h1>200 OK</h1>" in body_preview or "Service ready" in body_preview:
                    hint = (
                        " — This looks like an Odoo SaaS rate-limit response. "
                        "The server returned an HTML page instead of JSON. "
                        "Wait 30-60 seconds and retry, or restart the MCP server."
                    )
                # Cloudflare challenge page
                elif "cloudflare" in body_preview.lower() or "cf-" in response.headers.get("server", "").lower():
                    hint = (
                        " — This looks like a Cloudflare challenge/block. "
                        "The server may be rate-limiting requests. "
                        "Wait 60 seconds and retry."
                    )
                # Generic HTML (probably a proxy or load balancer error page)
                elif body_preview.startswith(("<!DOCTYPE", "<html", "<HTML")):
                    hint = (
                        " — The server returned an HTML page instead of JSON. "
                        "This may indicate a temporary rate-limit, proxy error, "
                        "or the endpoint is unreachable. Wait and retry."
                    )

                raise OdooConnectionError(
                    f"Invalid JSON response from server (HTTP {response.status_code}): {e}{hint}"
                ) from e

            if "error" in result:
                error = result["error"]
                msg = error.get("data", {}).get("message", error.get("message", str(error)))
                raise OdooExecutionError(f"Odoo error: {msg}")

            return result.get("result")

        except httpx.TimeoutException as e:
            raise OdooConnectionError(f"Connection timed out after {self.timeout}s: {e}") from e
        except httpx.RequestError as e:
            raise OdooConnectionError(f"Connection error: {e}") from e

    def authenticate(self) -> int:
        """Authenticate with the Odoo server via JSON-RPC."""
        if self._uid is not None:
            return self._uid

        try:
            uid = self._call("common", "authenticate", [self.database, self.user, self._password, {}])
        except OdooExecutionError as e:
            raise OdooAuthenticationError(str(e)) from e

        if not uid:
            raise OdooAuthenticationError(
                f"Authentication failed for user '{self.user}' on database '{self.database}'"
            )

        self._uid = uid
        return uid

    def execute_kw(self, model: str, method: str, args: Optional[list] = None, kwargs: Optional[dict] = None) -> Any:
        """Execute a method on an Odoo model via JSON-RPC."""
        uid = self.authenticate()
        args = args or []
        kwargs = kwargs or {}

        try:
            return self._call(
                "object",
                "execute_kw",
                [self.database, uid, self._password, model, method, args, kwargs],
            )
        except OdooExecutionError:
            raise


# ---------------------------------------------------------------------------
# Odoo 19+ JSON-2 REST client
# ---------------------------------------------------------------------------

# Maps (method_name) → (positional_arg_names, instance_method)
# instance_method=True means ids come from args[0] and are sent in body
_JSON2_METHOD_SIGNATURES: dict[str, tuple[list[str], bool]] = {
    "search": (["domain"], False),
    "search_read": (["domain"], False),
    "read": (["ids", "fields"], True),
    "write": (["ids", "vals"], True),
    "create": (["vals_list"], False),
    "unlink": (["ids"], True),
    "fields_get": (["attributes"], False),
    "export_data": (["ids", "fields_to_export", "raw_data"], True),
    "name_search": (["name"], False),
    "copy": (["ids"], True),
}


class Json2Client(BaseOdooClient):
    """REST client for Odoo 19+ /json/2 API endpoint.

    Uses Bearer token (API key) for authentication — no user/password per call.
    All method arguments are sent as named parameters in the JSON body.
    Model and method are encoded in the URL path.

    Reference:
        https://www.odoo.com/documentation/19.0/developer/reference/external_api.html

    Note:
        XML-RPC and JSON-RPC are deprecated in Odoo 19 and scheduled for
        removal in Odoo 22 (fall 2028). This client is the forward-compatible
        replacement.
    """

    def __init__(
        self,
        url: str,
        database: str,
        api_key: str | SecretStr,
        timeout: int = 120,
        # user/password accepted but ignored for backward compat with factory
        user: str = "",
        password: str | SecretStr = "",
    ) -> None:
        # BaseOdooClient requires user/password — pass empty strings
        super().__init__(
            url=normalize_url(url),
            database=database,
            user=user,
            password=password or SecretStr(""),
            timeout=timeout,
        )
        if isinstance(api_key, SecretStr):
            self._api_key: str = api_key.get_secret_value()
        else:
            self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        """Build the required HTTP headers for every JSON-2 request."""
        h = {
            "Authorization": f"bearer {self._api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "odoo-mcp-multi",
        }
        if self.database:
            h["X-Odoo-Database"] = self.database
        return h

    def _build_body(
        self,
        method: str,
        args: list,
        kwargs: dict,
    ) -> dict:
        """Translate positional args + kwargs into a named-parameter JSON body.

        JSON-2 does not support positional arguments — every parameter must be
        named.  We use ``_JSON2_METHOD_SIGNATURES`` for the 10 common ORM
        methods and fall back to a best-effort merge for unknown methods.
        """
        args = list(args or [])
        body: dict = dict(kwargs or {})

        sig = _JSON2_METHOD_SIGNATURES.get(method)
        if sig is not None:
            arg_names, is_instance = sig
            for i, name in enumerate(arg_names):
                if i < len(args):
                    body[name] = args[i]
            if is_instance and "ids" in body and body["ids"] is not None:
                # ids already populated from args[0] — keep it
                pass
            elif is_instance:
                # ids not provided — nothing to set
                pass
        else:
            # Unknown method: zip positional args with generic names
            for i, val in enumerate(args):
                body.setdefault(f"_arg{i}", val)

        return body

    def authenticate(self) -> None:  # type: ignore[override]
        """No-op: JSON-2 uses Bearer token — no UID needed."""
        return None

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list | None = None,
        kwargs: dict | None = None,
    ) -> object:
        """Execute an Odoo ORM method via the /json/2 REST endpoint."""
        url = f"{self.url}/json/2/{model}/{method}"
        body = self._build_body(method, args or [], kwargs or {})

        try:
            response = httpx.post(
                url,
                headers=self._headers(),
                json=body,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as e:
            raise OdooExecutionError(f"Request timed out: {e}") from e
        except httpx.RequestError as e:
            raise OdooConnectionError(f"Connection error: {e}") from e

        if response.status_code == 401:
            try:
                msg = response.json().get("message", "Unauthorized")
            except Exception:
                msg = response.text or "Unauthorized"
            raise OdooAuthenticationError(f"JSON-2 auth failed (401): {msg}")

        if response.status_code >= 400:
            try:
                err = response.json()
                msg = err.get("message", response.text)
            except Exception:
                msg = response.text
            raise OdooExecutionError(f"JSON-2 error ({response.status_code}): {msg}")

        return response.json()


class XmlRpcClient(BaseOdooClient):
    """XML-RPC client for legacy Odoo instances (6.1 - 19.0)."""

    @property
    def _common_endpoint(self) -> str:
        return f"{self.url}/xmlrpc/2/common"

    @property
    def _object_endpoint(self) -> str:
        return f"{self.url}/xmlrpc/2/object"

    def _get_transport(self) -> xmlrpc.client.Transport:
        """Create a transport with configured timeout."""
        transport = xmlrpc.client.SafeTransport() if self.url.startswith("https") else xmlrpc.client.Transport()
        original_make_connection = transport.make_connection

        def make_connection_with_timeout(host: str) -> Any:
            connection = original_make_connection(host)
            connection.timeout = self.timeout
            return connection

        transport.make_connection = make_connection_with_timeout
        return transport

    def _get_common(self) -> xmlrpc.client.ServerProxy:
        return xmlrpc.client.ServerProxy(self._common_endpoint, transport=self._get_transport(), allow_none=True)

    def _get_object(self) -> xmlrpc.client.ServerProxy:
        return xmlrpc.client.ServerProxy(self._object_endpoint, transport=self._get_transport(), allow_none=True)

    def authenticate(self) -> int:
        """Authenticate with the Odoo server via XML-RPC."""
        if self._uid is not None:
            return self._uid

        try:
            common = self._get_common()
            uid = common.authenticate(self.database, self.user, self._password, {})
        except socket.timeout as e:
            raise OdooConnectionError(f"Connection timed out: {e}") from e
        except ConnectionRefusedError as e:
            raise OdooConnectionError(f"Connection refused: {e}") from e
        except xmlrpc.client.Fault as e:
            raise OdooAuthenticationError(f"Authentication fault: {e.faultString}") from e
        except Exception as e:
            raise OdooConnectionError(f"Connection error: {e}") from e

        if not uid:
            raise OdooAuthenticationError(
                f"Authentication failed for user '{self.user}' on database '{self.database}'"
            )

        self._uid = uid
        return uid

    def execute_kw(self, model: str, method: str, args: Optional[list] = None, kwargs: Optional[dict] = None) -> Any:
        """Execute a method on an Odoo model via XML-RPC."""
        uid = self.authenticate()
        args = args or []
        kwargs = kwargs or {}

        try:
            obj = self._get_object()
            return obj.execute_kw(self.database, uid, self._password, model, method, args, kwargs)
        except socket.timeout as e:
            raise OdooExecutionError(f"Execution timed out: {e}") from e
        except xmlrpc.client.Fault as e:
            raise OdooExecutionError(f"Execution fault: {e.faultString}") from e
        except Exception as e:
            raise OdooExecutionError(f"Execution error: {e}") from e


def get_server_version(url: str, timeout: int = 30) -> Optional[dict]:
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


def detect_protocol(url: str, timeout: int = 30) -> Protocol:
    """Auto-detect the best protocol for an Odoo instance.

    Protocol selection logic:
    - Odoo 19.0+: JSON2S preferred
    - Odoo 8.0 - 18.x: JSONRPCS preferred
    - Odoo < 8.0 or unknown: XMLRPCS fallback
    """
    version_info = get_server_version(url, timeout)

    if version_info is None:
        return Protocol.XMLRPCS  # Can't detect, use legacy

    server_version = version_info.get("server_version", "")
    major, _, is_ent = parse_version(server_version)

    # Optional debugging
    import logging

    _logger = logging.getLogger(__name__)
    _logger.debug(f"Detected Odoo {'Enterprise' if is_ent else 'Community'} v{server_version}")

    if major >= 19:
        return Protocol.JSON2S
    if major >= 8:
        return Protocol.JSONRPCS

    return Protocol.XMLRPCS


def create_client(
    url: str,
    database: str,
    user: str = "",
    password: str | SecretStr = "",
    api_key: str | SecretStr = "",
    protocol: Protocol | str = Protocol.AUTO,
    timeout: int = 120,
) -> BaseOdooClient:
    """Create an appropriate Odoo client based on protocol.

    For Odoo ≥ 19 (JSON2/JSON2S), pass ``api_key`` instead of ``password``.
    For older versions (JSON-RPC, XML-RPC), pass ``user`` + ``password``.
    When ``protocol=AUTO``, the version is detected and the right client
    is selected automatically.

    Args:
        url: Odoo instance URL
        database: Database name
        user: Username (legacy auth — Odoo < 19)
        password: Password (legacy auth — Odoo < 19)
        api_key: Bearer API key (JSON-2 auth — Odoo ≥ 19)
        protocol: Protocol to use (auto, json2s, jsonrpcs, xmlrpcs, etc.)
        timeout: Request timeout in seconds

    Returns:
        Configured Odoo client instance
    """
    if isinstance(protocol, str):
        protocol = Protocol(protocol.lower())

    # Auto-detect if requested
    if protocol == Protocol.AUTO:
        protocol = detect_protocol(url, timeout=min(timeout, 30))

    # Odoo 19+ JSON-2 REST client
    if protocol in (Protocol.JSON2, Protocol.JSON2S):
        if not api_key:
            raise OdooAuthenticationError(
                "Protocol JSON2/JSON2S requires an 'api_key'. "
                "Generate one via Settings > Users > Account Security > API Keys."
            )
        return Json2Client(url=url, database=database, api_key=api_key, timeout=timeout)

    if protocol in (Protocol.JSONRPC, Protocol.JSONRPCS):
        return JsonRpcClient(url, database, user, password, timeout, use_json2=False)

    # XML-RPC fallback
    return XmlRpcClient(url, database, user, password, timeout)


# Alias for backward compatibility
OdooClient = create_client


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

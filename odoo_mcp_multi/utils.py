"""Multi-protocol client utilities for Odoo connections.

Provides a robust client for communicating with Odoo instances,
supporting XML-RPC (legacy), JSON-RPC (8.0+), and JSON2 (19.0+) protocols.
Includes automatic version detection for intelligent protocol selection.
"""

from __future__ import annotations

import json
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
            )
            try:
                result = response.json()
            except json.JSONDecodeError as e:
                raise OdooConnectionError(
                    f"Invalid JSON response from server (HTTP {response.status_code}): {e}"
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

    Tries JSON-RPC first, falls back to XML-RPC.
    Returns version dict or None if unreachable.
    """
    url = normalize_url(url)

    # Try JSON-RPC first (works for 8.0+)
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": "common", "method": "version", "args": []},
            "id": 1,
        }
        response = httpx.post(f"{url}/jsonrpc", json=payload, timeout=timeout)
        result = response.json()
        if "result" in result:
            return result["result"]
    except Exception:
        pass

    # Fall back to XML-RPC
    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        return common.version()
    except Exception:
        pass

    return None


def parse_version(version_str: str) -> tuple[int, int]:
    """Parse version string like '16.0' or 'saas~17.1' into (major, minor) tuple."""
    if not version_str:
        return (0, 0)

    # Handle saas~ prefix
    clean = version_str.replace("saas~", "").replace("saas-", "")

    parts = clean.split(".")
    try:
        major = int(parts[0]) if parts else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        return (major, minor)
    except ValueError:
        return (0, 0)


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
    major, _ = parse_version(server_version)

    if major >= 19:
        return Protocol.JSON2S
    if major >= 8:
        return Protocol.JSONRPCS

    return Protocol.XMLRPCS


def create_client(
    url: str,
    database: str,
    user: str,
    password: str | SecretStr,
    protocol: Protocol | str = Protocol.AUTO,
    timeout: int = 120,
) -> BaseOdooClient:
    """Create an appropriate Odoo client based on protocol.

    Args:
        url: Odoo instance URL
        database: Database name
        user: Username
        password: Password
        protocol: Protocol to use (auto, jsonrpcs, xmlrpcs, etc.)
        timeout: Request timeout in seconds

    Returns:
        Configured OdooClient instance
    """
    if isinstance(protocol, str):
        protocol = Protocol(protocol.lower())

    # Auto-detect if requested
    if protocol == Protocol.AUTO:
        protocol = detect_protocol(url, timeout=min(timeout, 30))

    # Create appropriate client
    if protocol in (Protocol.JSON2, Protocol.JSON2S):
        return JsonRpcClient(url, database, user, password, timeout, use_json2=True)

    if protocol in (Protocol.JSONRPC, Protocol.JSONRPCS):
        return JsonRpcClient(url, database, user, password, timeout, use_json2=False)

    # XML-RPC fallback
    return XmlRpcClient(url, database, user, password, timeout)


# Alias for backward compatibility
OdooClient = create_client


def parse_domain(domain_str: str) -> list:
    """Parse a domain string into a Python list."""
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


def parse_ids(ids_str: str) -> list[int]:
    """Parse an IDs string into a list of integers."""
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


def parse_json_arg(arg_str: str, default: Any = None) -> Any:
    """Parse a JSON argument string."""
    if not arg_str or arg_str.strip() in ("", "{}", "[]"):
        return default

    try:
        return json.loads(arg_str)
    except json.JSONDecodeError:
        try:
            import ast

            return ast.literal_eval(arg_str)
        except (ValueError, SyntaxError):
            return default

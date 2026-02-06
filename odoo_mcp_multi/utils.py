"""XML-RPC client utilities for Odoo connections.

Provides a robust XML-RPC client for communicating with Odoo instances,
with proper error handling and timeout management.
"""

from __future__ import annotations

import json
import socket
import xmlrpc.client
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import SecretStr


class OdooConnectionError(Exception):
    """Exception raised for Odoo connection failures."""

    pass


class OdooAuthenticationError(Exception):
    """Exception raised for authentication failures."""

    pass


class OdooExecutionError(Exception):
    """Exception raised for method execution failures."""

    pass


class OdooClient:
    """XML-RPC client for Odoo instances.

    Handles authentication and method execution via XML-RPC protocol.
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
            url: Odoo instance URL
            database: Database name
            user: Username
            password: Password (string or SecretStr)
            timeout: Request timeout in seconds
        """
        self.url = self._normalize_url(url)
        self.database = database
        self.user = user
        self._password = password.get_secret_value() if isinstance(password, SecretStr) else password
        self.timeout = timeout
        self._uid: Optional[int] = None

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Ensure URL has proper scheme and no trailing slash.

        Args:
            url: Raw URL string

        Returns:
            Normalized URL
        """
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return url.rstrip("/")

    @property
    def _common_endpoint(self) -> str:
        """Get the common XML-RPC endpoint URL."""
        return f"{self.url}/xmlrpc/2/common"

    @property
    def _object_endpoint(self) -> str:
        """Get the object XML-RPC endpoint URL."""
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
        """Get XML-RPC proxy for common endpoint."""
        return xmlrpc.client.ServerProxy(self._common_endpoint, transport=self._get_transport(), allow_none=True)

    def _get_object(self) -> xmlrpc.client.ServerProxy:
        """Get XML-RPC proxy for object endpoint."""
        return xmlrpc.client.ServerProxy(self._object_endpoint, transport=self._get_transport(), allow_none=True)

    def authenticate(self) -> int:
        """Authenticate with the Odoo server.

        Returns:
            User ID (uid) on success

        Raises:
            OdooAuthenticationError: If authentication fails
            OdooConnectionError: If connection fails
        """
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
            raise OdooAuthenticationError(f"Authentication failed for user '{self.user}' on database '{self.database}'")

        self._uid = uid
        return uid

    def execute_kw(
        self,
        model: str,
        method: str,
        args: Optional[list] = None,
        kwargs: Optional[dict] = None,
    ) -> Any:
        """Execute a method on an Odoo model.

        Args:
            model: Model name (e.g., 'res.partner')
            method: Method name (e.g., 'search_read')
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Method result

        Raises:
            OdooExecutionError: If execution fails
        """
        uid = self.authenticate()
        args = args or []
        kwargs = kwargs or {}

        try:
            obj = self._get_object()
            result = obj.execute_kw(self.database, uid, self._password, model, method, args, kwargs)
            return result
        except socket.timeout as e:
            raise OdooExecutionError(f"Execution timed out: {e}") from e
        except xmlrpc.client.Fault as e:
            raise OdooExecutionError(f"Execution fault: {e.faultString}") from e
        except Exception as e:
            raise OdooExecutionError(f"Execution error: {e}") from e

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
            model: Model name
            domain: Search domain (list of tuples)
            fields: Fields to read
            limit: Maximum records to return
            offset: Number of records to skip
            order: Sort order (e.g., 'name asc')

        Returns:
            List of record dictionaries
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
            model: Model name
            ids: Record IDs to update
            values: Field values to write

        Returns:
            True on success
        """
        return self.execute_kw(model, "write", [ids, values])

    def create(self, model: str, values: dict) -> int:
        """Create a new record.

        Args:
            model: Model name
            values: Field values for the new record

        Returns:
            ID of the created record
        """
        return self.execute_kw(model, "create", [values])

    def unlink(self, model: str, ids: list[int]) -> bool:
        """Delete records.

        Args:
            model: Model name
            ids: Record IDs to delete

        Returns:
            True on success
        """
        return self.execute_kw(model, "unlink", [ids])


def parse_domain(domain_str: str) -> list:
    """Parse a domain string into a Python list.

    Args:
        domain_str: Domain as string (e.g., "[('name', 'ilike', 'John')]")

    Returns:
        Parsed domain list

    Raises:
        ValueError: If parsing fails
    """
    if not domain_str or domain_str.strip() in ("", "[]"):
        return []

    try:
        # First try JSON parsing for simpler cases
        return json.loads(domain_str.replace("'", '"'))
    except json.JSONDecodeError:
        pass

    # Fall back to eval for tuple syntax (safer subset)
    try:
        # Use ast.literal_eval for safety
        import ast
        return ast.literal_eval(domain_str)
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"Invalid domain format: {domain_str}") from e


def parse_fields(fields_str: str) -> list[str]:
    """Parse a comma-separated fields string.

    Args:
        fields_str: Fields as comma-separated string (e.g., "name,email,phone")

    Returns:
        List of field names
    """
    if not fields_str or fields_str.strip() == "":
        return []

    return [f.strip() for f in fields_str.split(",") if f.strip()]


def parse_ids(ids_str: str) -> list[int]:
    """Parse an IDs string into a list of integers.

    Args:
        ids_str: IDs as string (e.g., "[1, 2, 3]" or "1,2,3")

    Returns:
        List of integer IDs
    """
    if not ids_str or ids_str.strip() == "":
        return []

    # Try JSON array format first
    try:
        result = json.loads(ids_str)
        if isinstance(result, list):
            return [int(i) for i in result]
        return [int(result)]
    except json.JSONDecodeError:
        pass

    # Fall back to comma-separated format
    return [int(i.strip()) for i in ids_str.split(",") if i.strip()]


def parse_json_arg(arg_str: str, default: Any = None) -> Any:
    """Parse a JSON argument string.

    Args:
        arg_str: JSON string
        default: Default value if parsing fails or empty

    Returns:
        Parsed value or default
    """
    if not arg_str or arg_str.strip() in ("", "{}", "[]"):
        return default

    try:
        return json.loads(arg_str)
    except json.JSONDecodeError:
        # Try ast.literal_eval for Python-style dicts
        try:
            import ast
            return ast.literal_eval(arg_str)
        except (ValueError, SyntaxError):
            return default

"""Multi-protocol RPC clients for Odoo connections.

Provides concrete client implementations for XML-RPC, JSON-RPC, and
JSON-2 (Odoo 19+) protocols, plus a factory function that auto-selects
the right client based on server version.
"""

from __future__ import annotations

import json
import socket
import xmlrpc.client
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx
from pydantic import SecretStr

from odoo_mcp_multi.exceptions import (
    OdooAuthenticationError,
    OdooConnectionError,
    OdooExecutionError,
)
from odoo_mcp_multi.parsers import normalize_url
from odoo_mcp_multi.version import Protocol, detect_protocol


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
        verify: bool = True,
    ) -> None:
        """Initialize the Odoo client.

        Args:
            url: Odoo instance URL (e.g., 'https://odoo.example.com')
            database: Database name to connect to
            user: Username for authentication
            password: Password for authentication (string or SecretStr)
            timeout: Request timeout in seconds (default: 120)
            verify: Verify SSL certificates (default: True)
        """
        self.url = normalize_url(url)
        self.database = database
        self.user = user
        self._password = password.get_secret_value() if isinstance(password, SecretStr) else password
        self.timeout = timeout
        self.verify = verify
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


def _diagnose_non_json_response(response: httpx.Response) -> str:
    """Produce a human-readable hint when Odoo returns non-JSON content.

    Sniffs the response body for common patterns (SaaS rate-limit pages,
    Cloudflare challenges, generic HTML error pages) and returns a
    diagnostic suffix string for error messages.
    """
    body_preview = response.text[:500].strip()

    if "<h1>200 OK</h1>" in body_preview or "Service ready" in body_preview:
        return (
            " — This looks like an Odoo SaaS rate-limit response. "
            "The server returned an HTML page instead of JSON. "
            "Wait 30-60 seconds and retry, or restart the MCP server."
        )

    if "cloudflare" in body_preview.lower() or "cf-" in response.headers.get("server", "").lower():
        return (
            " — This looks like a Cloudflare challenge/block. "
            "The server may be rate-limiting requests. "
            "Wait 60 seconds and retry."
        )

    if body_preview.startswith(("<!DOCTYPE", "<html", "<HTML")):
        return (
            " — The server returned an HTML page instead of JSON. "
            "This may indicate a temporary rate-limit, proxy error, "
            "or the endpoint is unreachable. Wait and retry."
        )

    return ""


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
        verify: bool = True,
    ) -> None:
        """Initialize the JSON-RPC client.

        Args:
            url: Odoo instance URL
            database: Database name
            user: Username for authentication
            password: Password for authentication
            timeout: Request timeout in seconds (default: 120)
            use_json2: Use JSON2 protocol for Odoo 19.0+ (default: False)
            verify: Verify SSL certificates (default: True)
        """
        super().__init__(url, database, user, password, timeout, verify=verify)
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
                verify=self.verify,
                headers={"User-Agent": "odoo-mcp-multi"},
            )
        except httpx.TimeoutException as e:
            raise OdooConnectionError(f"Connection timed out after {self.timeout}s: {e}") from e
        except httpx.RequestError as e:
            raise OdooConnectionError(f"Connection error: {e}") from e

        try:
            result = response.json()
        except json.JSONDecodeError as e:
            hint = _diagnose_non_json_response(response)
            raise OdooConnectionError(
                f"Invalid JSON response from server (HTTP {response.status_code}): {e}{hint}"
            ) from e

        if "error" in result:
            error = result["error"]
            msg = error.get("data", {}).get("message", error.get("message", str(error)))
            raise OdooExecutionError(f"Odoo error: {msg}")

        return result.get("result")

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

# Sentinel object to distinguish between a cache miss and a cached None value
_CACHE_MISS = object()

# Maps (method_name) → (positional_arg_names, instance_method)
# instance_method=True means ids come from args[0] and are sent in body
_JSON2_METHOD_SIGNATURES: dict[str, tuple[list[str], bool]] = {
    "search": (["domain"], False),
    "search_count": (["domain"], False),
    "search_read": (["domain"], False),
    "read": (["ids", "fields"], True),
    "write": (["ids", "vals"], True),
    "create": (["vals_list"], False),
    "unlink": (["ids"], True),
    "fields_get": (["attributes"], False),
    "export_data": (["ids", "fields_to_export", "raw_data"], True),
    "name_search": (["name"], False),
    "name_get": (["ids"], True),
    "default_get": (["fields_list"], False),
    "copy": (["ids"], True),
    "check_access_rights": (["operation"], False),
    "check_access_rule": (["ids", "operation"], True),
    "load": (["fields", "data"], False),
    "message_post": (["ids", "body", "subject"], True),
    "activity_schedule": (["ids", "activity_type_xmlid"], True),
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
        verify: bool = True,
    ) -> None:
        # BaseOdooClient requires user/password — pass empty strings
        super().__init__(
            url=normalize_url(url),
            database=database,
            user=user,
            password=password or SecretStr(""),
            timeout=timeout,
            verify=verify,
        )
        if isinstance(api_key, SecretStr):
            self._api_key: str = api_key.get_secret_value()
        else:
            self._api_key = api_key
        # We cache Odoo endpoint method signatures (mapped by model -> method) to avoid redundant network
        # round-trips because the Odoo environment metadata remains static during the client lifecycle.
        self._signatures_cache: dict[str, dict[str, tuple[list[str], bool] | None]] = {}

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

    def _fetch_method_signature(self, model: str, method: str) -> tuple[list[str], bool] | None:
        """Fetch the signature for a given method dynamically using Odoo's reflection API.

        This method queries the Bearer-authenticated ``/doc-bearer/<model>.json`` endpoint on the Odoo
        server. It parses the JSON schema representation of the model's methods to extract parameter
        names and determine if the method is an instance method or a class/model method.

        Version Compatibility:
            The ``/doc-bearer/<model>.json`` reflection endpoint is only available on **Odoo 19.0 and
            later**, introduced alongside the JSON-2 REST protocol. On older Odoo versions (≤ 18.x),
            this endpoint does not exist and will respond with a 404 (or similar 4xx) status code.
            In that case, this method returns ``None`` and the caller falls back to the local heuristic
            defined in ``_build_body``.

            +-----------------+------------------------------------+
            | Odoo version    | /doc-bearer/<model>.json available |
            +=================+====================================+
            | 19.0+           | Yes (JSON-2 protocol)              |
            +-----------------+------------------------------------+
            | 8.0 – 18.x      | No (404 expected)                  |
            +-----------------+------------------------------------+

        To increase resilience in unstable network environments, it implements up to 3 attempts with
        exponential backoff (1s, 2s) for transient HTTP errors and network timeouts.

        Parameters:
            model: The name of the Odoo model (e.g., "res.partner").
            method: The name of the method to inspect (e.g., "message_post").

        Returns:
            A tuple of ``(arg_names, is_instance_method)`` if successfully retrieved and parsed.
            Specifically:
            - ``arg_names`` is a list of positional argument names (e.g., ``["ids", "body", "subject"]``).
            - ``is_instance_method`` is a boolean indicating if the method acts on specific record IDs.
            Returns ``None`` if:
            - The reflection API endpoint is unavailable (e.g., Odoo < 19.0).
            - The model or method does not exist or has no defined schema.
            - All retry attempts fail due to network errors, timeouts, or transient 5xx server errors.
            - The response payload is not valid JSON.

        Exceptions Handled:
            - ``httpx.RequestError``: Caught during network timeouts or connection issues; triggers retry/fallback.
            - ``json.JSONDecodeError``: Caught if the server response is not valid JSON; returns None.
            - ``KeyError``, ``AttributeError``: Caught if the JSON structure does not match the
              expected Odoo schema format; returns None.

        Examples:
            >>> client = Json2Client("https://odoo.example.com", "my_db", "my_api_key")
            >>> client._fetch_method_signature("res.partner", "message_post")
            (["ids", "body", "subject"], True)

            >>> client._fetch_method_signature("res.partner", "create")
            (["vals_list"], False)
        """
        import time

        url = f"{self.url}/doc-bearer/{model}.json"
        attempts = 3
        delay = 1.0

        for attempt in range(attempts):
            try:
                response = httpx.get(
                    url,
                    headers=self._headers(),
                    timeout=self.timeout,
                    verify=self.verify,
                )
                if response.status_code == 200:
                    try:
                        data = response.json()
                        method_info = data.get("methods", {}).get(method)
                        if not method_info:
                            return None

                        is_instance = "model" not in method_info.get("api", [])
                        arg_names = list(method_info.get("parameters", {}).keys())
                        if is_instance:
                            arg_names = ["ids"] + arg_names
                        return arg_names, is_instance
                    except (json.JSONDecodeError, KeyError, AttributeError):
                        return None

                # For client errors other than 429 (rate-limit), retry won't help.
                # A 404 is the expected response from Odoo versions < 19.0 that
                # do not implement the /doc-bearer reflection API.
                if response.status_code < 500 and response.status_code != 429:
                    return None
            except httpx.RequestError:
                if attempt == attempts - 1:
                    return None
            except Exception:
                return None

            if attempt < attempts - 1:
                time.sleep(delay)
                delay *= 2.0

        return None

    def _build_body(
        self,
        model: str,
        method: str,
        args: list,
        kwargs: dict,
    ) -> dict:
        """Translate positional args + kwargs into a named-parameter JSON body.

        JSON-2 does not support positional arguments — every parameter must be
        named. We use ``_JSON2_METHOD_SIGNATURES`` for the 10 common ORM
        methods and fall back to dynamic introspection or smart local heuristics
        for unknown methods.
        """
        if not model or not isinstance(model, str):
            raise ValueError("The 'model' parameter must be a non-empty string.")

        args = list(args or [])
        body: dict = dict(kwargs or {})

        sig = _JSON2_METHOD_SIGNATURES.get(method)
        if sig is None:
            if model not in self._signatures_cache:
                self._signatures_cache[model] = {}
            # We use the _CACHE_MISS sentinel object to distinguish a cache miss
            # (key not queried yet) from a valid None value (queried but not found).
            cached_sig = self._signatures_cache[model].get(method, _CACHE_MISS)
            if cached_sig is _CACHE_MISS:
                sig = self._fetch_method_signature(model, method)
                self._signatures_cache[model][method] = sig
            else:
                sig = cached_sig

        if sig is not None:
            arg_names, _ = sig
            for i, name in enumerate(arg_names):
                if i < len(args):
                    body[name] = args[i]
            return body

        # If /doc-bearer API is unavailable (e.g. Odoo < 19 or missing api_doc), we use a deterministic
        # local heuristic: if the first argument represents database record ID(s), we treat it as an
        # instance method mapping to "ids".
        first_arg = args[0] if args else None
        is_instance = False
        if isinstance(first_arg, int):
            is_instance = True
        elif isinstance(first_arg, list) and all(isinstance(x, int) for x in first_arg):
            is_instance = True

        if is_instance:
            body["ids"] = args[0]
            for i, val in enumerate(args[1:]):
                body[f"_arg{i}"] = val
            return body

        for i, val in enumerate(args):
            body[f"_arg{i}"] = val
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
        if not model or not isinstance(model, str):
            raise ValueError("The 'model' parameter must be a non-empty string.")
        if not method or not isinstance(method, str):
            raise ValueError("The 'method' parameter must be a non-empty string.")

        url = f"{self.url}/json/2/{model}/{method}"
        body = self._build_body(model, method, args or [], kwargs or {})

        try:
            response = httpx.post(
                url,
                headers=self._headers(),
                json=body,
                timeout=self.timeout,
                verify=self.verify,
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
        """Create a transport with configured timeout and SSL verification settings."""
        if self.url.startswith("https"):
            import ssl

            context = None if self.verify else ssl._create_unverified_context()
            transport = xmlrpc.client.SafeTransport(context=context)
        else:
            transport = xmlrpc.client.Transport()
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


def create_client(
    url: str,
    database: str,
    user: str = "",
    password: str | SecretStr = "",
    api_key: str | SecretStr = "",
    protocol: Protocol | str = Protocol.AUTO,
    timeout: int = 120,
    verify: bool = True,
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
        verify: Verify SSL certificates (default: True)

    Returns:
        Configured Odoo client instance
    """
    if isinstance(protocol, str):
        protocol = Protocol(protocol.lower())

    if protocol == Protocol.AUTO:
        protocol = detect_protocol(url, timeout=min(timeout, 30), verify=verify)

    # JSON-2 requires an API key — fail fast before constructing the client
    if protocol in (Protocol.JSON2, Protocol.JSON2S) and not api_key:
        raise OdooAuthenticationError(
            "Protocol JSON2/JSON2S requires an 'api_key'. "
            "Generate one via Settings > Users > Account Security > API Keys."
        )

    if protocol in (Protocol.JSON2, Protocol.JSON2S):
        return Json2Client(
            url=url,
            database=database,
            api_key=api_key,
            timeout=timeout,
            verify=verify,
        )

    if protocol in (Protocol.JSONRPC, Protocol.JSONRPCS):
        return JsonRpcClient(
            url=url,
            database=database,
            user=user,
            password=password,
            timeout=timeout,
            verify=verify,
            use_json2=False,
        )

    return XmlRpcClient(
        url=url,
        database=database,
        user=user,
        password=password,
        timeout=timeout,
        verify=verify,
    )


# Alias for backward compatibility
OdooClient = create_client

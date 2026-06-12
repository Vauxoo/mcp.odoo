"""Tests for pure utility functions in utils.py.

These functions have no I/O and no network — they are deterministic pure
functions. Tests here verify edge cases that matter in real production
Odoo environments (saas~ versions, URL normalization, protocol selection).
"""

from unittest.mock import patch

import pytest

from odoo_mcp_multi.utils import (
    Json2Client,
    JsonRpcClient,
    Protocol,
    XmlRpcClient,
    create_client,
    detect_protocol,
    normalize_url,
    parse_fields,
    parse_version,
)

# ---------------------------------------------------------------------------
# normalize_url
# ---------------------------------------------------------------------------


class TestNormalizeUrl:
    def test_adds_https_when_no_scheme(self):
        assert normalize_url("odoo.example.com") == "https://odoo.example.com"

    def test_preserves_existing_https(self):
        assert normalize_url("https://odoo.example.com") == "https://odoo.example.com"

    def test_preserves_existing_http(self):
        assert normalize_url("http://odoo.example.com") == "http://odoo.example.com"

    def test_strips_trailing_slash(self):
        assert normalize_url("https://odoo.example.com/") == "https://odoo.example.com"

    def test_strips_multiple_trailing_slashes(self):
        assert normalize_url("https://odoo.example.com///") == "https://odoo.example.com"

    def test_preserves_port(self):
        assert normalize_url("https://odoo.example.com:8069") == "https://odoo.example.com:8069"

    def test_bare_domain_with_port(self):
        assert normalize_url("odoo.example.com:8069") == "https://odoo.example.com:8069"


# ---------------------------------------------------------------------------
# parse_version
# ---------------------------------------------------------------------------


class TestParseVersion:
    def test_standard_major_minor(self):
        assert parse_version("16.0") == (16, 0, False)

    def test_major_only_with_zero(self):
        assert parse_version("17.0") == (17, 0, False)

    def test_saas_tilde_prefix(self):
        """saas~17.1 is common in Odoo SaaS — must parse correctly."""
        assert parse_version("saas~17.1") == (17, 1, False)

    def test_saas_dash_prefix(self):
        assert parse_version("saas-16.3") == (16, 3, False)

    def test_empty_string(self):
        assert parse_version("") == (0, 0, False)

    def test_major_version_19(self):
        assert parse_version("19.0") == (19, 0, False)

    def test_old_version_12(self):
        assert parse_version("12.0") == (12, 0, False)

    def test_non_numeric_returns_zero(self):
        assert parse_version("unknown") == (0, 0, False)

    def test_single_digit_only(self):
        # "16" with no minor — minor defaults to 0
        assert parse_version("16") == (16, 0, False)

    def test_enterprise_suffix(self):
        assert parse_version("19.0+e") == (19, 0, True)
        assert parse_version("saas~17.4+e") == (17, 4, True)
        assert parse_version("16.0+E") == (16, 0, True)


# ---------------------------------------------------------------------------
# parse_fields
# ---------------------------------------------------------------------------


class TestParseFields:
    def test_basic_fields(self):
        assert parse_fields("name,email,phone") == ["name", "email", "phone"]

    def test_strips_whitespace(self):
        assert parse_fields(" name , email , phone ") == ["name", "email", "phone"]

    def test_empty_string(self):
        assert parse_fields("") == []

    def test_whitespace_only(self):
        assert parse_fields("   ") == []

    def test_single_field(self):
        assert parse_fields("name") == ["name"]

    def test_relational_field_syntax(self):
        """id/id syntax for External IDs must be preserved."""
        assert parse_fields("id,name,country_id/id") == ["id", "name", "country_id/id"]


# ---------------------------------------------------------------------------
# detect_protocol
# ---------------------------------------------------------------------------


class TestDetectProtocol:
    @patch("odoo_mcp_multi.version.get_server_version")
    def test_odoo_19_returns_json2s(self, mock_version):
        mock_version.return_value = {"server_version": "19.0"}
        assert detect_protocol("https://x.com") == Protocol.JSON2S

    @patch("odoo_mcp_multi.version.get_server_version")
    def test_odoo_17_returns_jsonrpcs(self, mock_version):
        mock_version.return_value = {"server_version": "17.0"}
        assert detect_protocol("https://x.com") == Protocol.JSONRPCS

    @patch("odoo_mcp_multi.version.get_server_version")
    def test_odoo_12_returns_jsonrpcs(self, mock_version):
        mock_version.return_value = {"server_version": "12.0"}
        assert detect_protocol("https://x.com") == Protocol.JSONRPCS

    @patch("odoo_mcp_multi.version.get_server_version")
    def test_saas_version_17_returns_jsonrpcs(self, mock_version):
        mock_version.return_value = {"server_version": "saas~17.1"}
        assert detect_protocol("https://x.com") == Protocol.JSONRPCS

    @patch("odoo_mcp_multi.version.get_server_version")
    def test_unreachable_server_returns_xmlrpcs(self, mock_version):
        """If server is unreachable, fall back to XML-RPC (most compatible)."""
        mock_version.return_value = None
        assert detect_protocol("https://x.com") == Protocol.XMLRPCS

    @patch("odoo_mcp_multi.version.get_server_version")
    def test_unknown_version_returns_xmlrpcs(self, mock_version):
        mock_version.return_value = {"server_version": "unknown"}
        assert detect_protocol("https://x.com") == Protocol.XMLRPCS


# ---------------------------------------------------------------------------
# create_client (factory)
# ---------------------------------------------------------------------------


class TestCreateClient:
    def test_jsonrpcs_returns_jsonrpc_client(self):
        client = create_client("https://x.com", "db", user="user", password="pass", protocol=Protocol.JSONRPCS)
        assert isinstance(client, JsonRpcClient)
        assert client.use_json2 is False

    def test_jsonrpc_returns_jsonrpc_client(self):
        client = create_client("https://x.com", "db", user="user", password="pass", protocol=Protocol.JSONRPC)
        assert isinstance(client, JsonRpcClient)
        assert client.use_json2 is False

    def test_json2s_returns_json2_client(self):
        """JSON2S now returns the real Json2Client (Bearer token REST client)."""
        client = create_client("https://x.com", "db", api_key="mykey", protocol=Protocol.JSON2S)
        assert isinstance(client, Json2Client)

    def test_json2_returns_json2_client(self):
        """JSON2 now returns the real Json2Client (Bearer token REST client)."""
        client = create_client("https://x.com", "db", api_key="mykey", protocol=Protocol.JSON2)
        assert isinstance(client, Json2Client)

    def test_json2s_without_api_key_raises(self):
        """JSON2S without api_key must raise OdooAuthenticationError immediately."""
        from odoo_mcp_multi.utils import OdooAuthenticationError

        with pytest.raises(OdooAuthenticationError, match="api_key"):
            create_client("https://x.com", "db", protocol=Protocol.JSON2S)

    def test_xmlrpcs_returns_xmlrpc_client(self):
        client = create_client("https://x.com", "db", user="user", password="pass", protocol=Protocol.XMLRPCS)
        assert isinstance(client, XmlRpcClient)

    def test_string_protocol_is_accepted(self):
        """Protocol can be passed as a string (common in profile config)."""
        client = create_client("https://x.com", "db", user="user", password="pass", protocol="jsonrpcs")
        assert isinstance(client, JsonRpcClient)

    @patch("odoo_mcp_multi.client.detect_protocol")
    def test_auto_delegates_to_detect_protocol(self, mock_detect):
        mock_detect.return_value = Protocol.JSONRPCS
        client = create_client("https://x.com", "db", user="user", password="pass", protocol=Protocol.AUTO)
        assert isinstance(client, JsonRpcClient)
        mock_detect.assert_called_once()

    def test_url_is_normalized(self):
        """URL without scheme should be normalized before reaching the client."""
        client = create_client("odoo.example.com", "db", user="user", password="pass", protocol=Protocol.JSONRPCS)
        assert client.url == "https://odoo.example.com"


# ---------------------------------------------------------------------------
# JsonRpcClient endpoint configuration
# ---------------------------------------------------------------------------


class TestJsonRpcClientEndpoint:
    def test_standard_endpoint(self):
        client = JsonRpcClient("https://x.com", "db", "user", "pass", use_json2=False)
        assert client._endpoint == "/jsonrpc"

    def test_json2_endpoint(self):
        client = JsonRpcClient("https://x.com", "db", "user", "pass", use_json2=True)
        assert client._endpoint == "/jsonrpc/2"

    def test_uid_initially_none(self):
        client = JsonRpcClient("https://x.com", "db", "user", "pass")
        assert client._uid is None

    def test_authenticate_uses_cached_uid(self):
        """If _uid is already set, authenticate() must return it without HTTP."""
        client = JsonRpcClient("https://x.com", "db", "user", "pass")
        client._uid = 7
        result = client.authenticate()
        assert result == 7


# ---------------------------------------------------------------------------
# Json2Client._build_body — pure transformation, no I/O
# ---------------------------------------------------------------------------


class TestJson2ClientBuildBody:
    """_build_body translates positional args into named params for JSON-2."""

    def _make_client(self):
        return Json2Client(url="https://x.com", database="db", api_key="key")

    def test_known_method_maps_args_by_name(self):
        """search_read([domain]) → {domain: domain}."""
        client = self._make_client()
        body = client._build_body("res.partner", "search_read", [[("active", "=", True)]], {})
        assert body == {"domain": [("active", "=", True)]}

    def test_known_method_with_kwargs(self):
        """kwargs are merged into body alongside mapped args."""
        client = self._make_client()
        body = client._build_body("res.partner", "search_read", [[]], {"limit": 10, "fields": ["name"]})
        assert body["domain"] == []
        assert body["limit"] == 10
        assert body["fields"] == ["name"]

    def test_known_method_fewer_args_than_signature(self):
        """If fewer args than the signature expects, only map what's provided."""
        client = self._make_client()
        body = client._build_body("res.partner", "read", [], {})
        assert "ids" not in body

    def test_unknown_method_uses_generic_arg_names(self):
        """Unknown methods get _arg0, _arg1, etc."""
        client = self._make_client()
        body = client._build_body("res.partner", "custom_method", ["a", "b"], {"key": "val"})
        assert body["_arg0"] == "a"
        assert body["_arg1"] == "b"
        assert body["key"] == "val"

    def test_unknown_method_no_args(self):
        """Unknown method with no args returns just kwargs."""
        client = self._make_client()
        body = client._build_body("res.partner", "ping", [], {"check": True})
        assert body == {"check": True}

    def test_write_maps_ids_and_vals(self):
        """write([ids, vals]) → {ids: [...], vals: {...}}."""
        client = self._make_client()
        body = client._build_body("res.partner", "write", [[1, 2], {"name": "X"}], {})
        assert body["ids"] == [1, 2]
        assert body["vals"] == {"name": "X"}

    def test_authenticate_is_noop(self):
        """JSON-2 uses Bearer token — authenticate returns None."""
        client = self._make_client()
        assert client.authenticate() is None

    def test_headers_include_bearer_and_database(self):
        client = self._make_client()
        h = client._headers()
        assert h["Authorization"] == "bearer key"
        assert h["X-Odoo-Database"] == "db"

    def test_headers_omit_database_when_empty(self):
        client = Json2Client(url="https://x.com", database="", api_key="key")
        h = client._headers()
        assert "X-Odoo-Database" not in h

    def test_build_body_invalid_model(self):
        """Passing an empty or non-string model must raise ValueError."""
        client = self._make_client()
        with pytest.raises(ValueError, match="The 'model' parameter must be a non-empty string."):
            client._build_body("", "search_read", [], {})
        with pytest.raises(ValueError, match="The 'model' parameter must be a non-empty string."):
            client._build_body(None, "search_read", [], {})  # type: ignore[arg-type]


class TestJson2ClientExecuteKw:
    """Tests for Json2Client.execute_kw validation logic."""

    def test_execute_kw_invalid_model_or_method(self):
        client = Json2Client(url="https://x.com", database="db", api_key="key")
        with pytest.raises(ValueError, match="The 'model' parameter must be a non-empty string."):
            client.execute_kw("", "search")
        with pytest.raises(ValueError, match="The 'model' parameter must be a non-empty string."):
            client.execute_kw(None, "search")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="The 'method' parameter must be a non-empty string."):
            client.execute_kw("res.partner", "")
        with pytest.raises(ValueError, match="The 'method' parameter must be a non-empty string."):
            client.execute_kw("res.partner", None)  # type: ignore[arg-type]

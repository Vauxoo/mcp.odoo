"""Error-branch tests for client.py.

Covers the network failure paths that never fire in the happy-path
suites: timeouts, connection errors, XML-RPC faults, non-JSON bodies,
JSON-2 signature-introspection fallbacks, and the SSL heuristics. All
network layers are mocked — no sockets are opened.
"""

import socket
import ssl
import xmlrpc.client
from unittest.mock import MagicMock, patch

import httpx
import pytest

from odoo_mcp_multi.client import (
    Json2Client,
    JsonRpcClient,
    XmlRpcClient,
    _diagnose_non_json_response,
    is_ssl_verification_error,
)
from odoo_mcp_multi.exceptions import (
    OdooAuthenticationError,
    OdooConnectionError,
    OdooExecutionError,
    OdooMethodNotFoundError,
)

URL = "https://odoo.test"


def _response(status: int, json_body=None, text: str = "") -> httpx.Response:
    request = httpx.Request("POST", f"{URL}/jsonrpc")
    if json_body is not None:
        return httpx.Response(status, json=json_body, request=request)
    return httpx.Response(status, text=text, request=request)


def _jsonrpc_client(**kw) -> JsonRpcClient:
    return JsonRpcClient(URL, "db", "admin", "secret", **kw)


def _json2_client(**kw) -> Json2Client:
    return Json2Client(URL, "db", api_key="key", **kw)


def _xmlrpc_client(url: str = URL, **kw) -> XmlRpcClient:
    return XmlRpcClient(url, "db", "admin", "secret", **kw)


# ---------------------------------------------------------------------------
# is_ssl_verification_error heuristics
# ---------------------------------------------------------------------------


def test_ssl_error_detected_by_class_name():
    class SSLCertVerificationErrorLike(Exception):
        pass

    assert is_ssl_verification_error(SSLCertVerificationErrorLike("boom")) is True


def test_ssl_error_with_unrelated_reason_is_not_verification():
    err = ssl.SSLError()
    err.reason = "WRONG_VERSION_NUMBER"
    assert is_ssl_verification_error(err) is False


# ---------------------------------------------------------------------------
# BaseOdooClient convenience wrappers
# ---------------------------------------------------------------------------


def test_base_client_wrappers_delegate_to_execute_kw():
    client = _jsonrpc_client()
    client.execute_kw = MagicMock(return_value="ok")

    client.search_read("res.partner", [("a", "=", 1)], fields=["name"], limit=5, offset=2, order="name asc")
    client.execute_kw.assert_called_with(
        "res.partner",
        "search_read",
        [[("a", "=", 1)]],
        {"limit": 5, "offset": 2, "fields": ["name"], "order": "name asc"},
    )

    client.search_read("res.partner")
    client.execute_kw.assert_called_with("res.partner", "search_read", [[]], {"limit": 100, "offset": 0})

    client.write("res.partner", [1], {"name": "x"})
    client.execute_kw.assert_called_with("res.partner", "write", [[1], {"name": "x"}], {})

    client.create("res.partner", {"name": "x"})
    client.execute_kw.assert_called_with("res.partner", "create", [{"name": "x"}], {})

    client.unlink("res.partner", [1])
    client.execute_kw.assert_called_with("res.partner", "unlink", [[1]], {})


def test_get_server_version_falls_back_to_base_module():
    client = _jsonrpc_client()
    client.execute_kw = MagicMock(return_value=[{"latest_version": "17.0.1.0.0"}])
    with patch("odoo_mcp_multi.client.get_server_version", return_value={"no_version_key": True}):
        assert client.get_server_version() == "17.0.1.0.0"


def test_get_server_version_unknown_when_all_probes_fail():
    client = _jsonrpc_client()
    client.execute_kw = MagicMock(return_value=[])
    with patch("odoo_mcp_multi.client.get_server_version", return_value=None):
        assert client.get_server_version() == "unknown"


# ---------------------------------------------------------------------------
# _diagnose_non_json_response
# ---------------------------------------------------------------------------


def test_diagnose_plain_text_has_no_hint():
    assert _diagnose_non_json_response(_response(200, text="just some text")) == ""


# ---------------------------------------------------------------------------
# JsonRpcClient error branches
# ---------------------------------------------------------------------------


def test_jsonrpc_post_timeout_raises_connection_error():
    client = _jsonrpc_client()
    with patch("odoo_mcp_multi.client.httpx.post", side_effect=httpx.TimeoutException("slow")):
        with pytest.raises(OdooConnectionError, match="timed out"):
            client._post(f"{URL}/jsonrpc", {})


def test_jsonrpc_post_network_error_raises_connection_error():
    client = _jsonrpc_client()
    with patch("odoo_mcp_multi.client.httpx.post", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(OdooConnectionError, match="Connection error"):
            client._post(f"{URL}/jsonrpc", {})


def test_jsonrpc_call_maps_missing_method_error():
    client = _jsonrpc_client()
    body = {"error": {"data": {"message": "'res.partner' object has no attribute 'foo'"}}}
    with patch.object(client, "_post", return_value=_response(200, json_body=body)):
        with pytest.raises(OdooMethodNotFoundError):
            client._call("object", "execute_kw", [])


def test_jsonrpc_call_maps_generic_error():
    client = _jsonrpc_client()
    body = {"error": {"message": "Access Denied"}}
    with patch.object(client, "_post", return_value=_response(200, json_body=body)):
        with pytest.raises(OdooExecutionError, match="Access Denied"):
            client._call("common", "authenticate", [])


def test_jsonrpc_authenticate_wraps_execution_error():
    client = _jsonrpc_client()
    with patch.object(client, "_call", side_effect=OdooExecutionError("bad credentials")):
        with pytest.raises(OdooAuthenticationError, match="bad credentials"):
            client.authenticate()


def test_jsonrpc_authenticate_rejects_falsy_uid():
    client = _jsonrpc_client()
    with patch.object(client, "_call", return_value=False):
        with pytest.raises(OdooAuthenticationError, match="Authentication failed"):
            client.authenticate()


def test_jsonrpc_execute_kw_propagates_execution_error():
    client = _jsonrpc_client()
    client._uid = 1
    with patch.object(client, "_call", side_effect=OdooExecutionError("boom")):
        with pytest.raises(OdooExecutionError, match="boom"):
            client.execute_kw("res.partner", "read", [[1]], {})


# ---------------------------------------------------------------------------
# Json2Client error branches
# ---------------------------------------------------------------------------


def test_json2_fetch_signature_unknown_method_returns_none():
    client = _json2_client()
    response = _response(200, json_body={"methods": {}})
    with patch("odoo_mcp_multi.client.httpx.get", return_value=response):
        assert client._fetch_method_signature("res.partner", "nope") is None


def test_json2_fetch_signature_model_method_keeps_args():
    client = _json2_client()
    body = {"methods": {"create": {"api": ["model"], "parameters": {"vals_list": {}}}}}
    with patch("odoo_mcp_multi.client.httpx.get", return_value=_response(200, json_body=body)):
        assert client._fetch_method_signature("res.partner", "create") == (["vals_list"], False)


def test_json2_fetch_signature_gives_up_after_retries():
    client = _json2_client()
    with patch("odoo_mcp_multi.client.httpx.get", side_effect=httpx.ConnectError("down")):
        with patch("odoo_mcp_multi.client.time.sleep") as mock_sleep:
            assert client._fetch_method_signature("res.partner", "read") is None
    assert mock_sleep.call_count == 2


def test_json2_fetch_signature_swallows_unexpected_errors():
    client = _json2_client()
    with patch("odoo_mcp_multi.client.httpx.get", side_effect=RuntimeError("weird")):
        assert client._fetch_method_signature("res.partner", "read") is None


def test_json2_build_body_heuristic_maps_int_first_arg_to_ids():
    client = _json2_client()
    with patch.object(client, "_fetch_method_signature", return_value=None):
        body = client._build_body("res.partner", "custom_action", [5, "extra"], {"ctx": 1})
    assert body == {"ctx": 1, "ids": 5, "_arg0": "extra"}


def test_json2_post_timeout_raises_execution_error():
    client = _json2_client()
    with patch("odoo_mcp_multi.client.httpx.post", side_effect=httpx.TimeoutException("slow")):
        with pytest.raises(OdooExecutionError, match="timed out"):
            client._post(f"{URL}/json/2/res.partner/read", {})


def test_json2_post_network_error_raises_connection_error():
    client = _json2_client()
    with patch("odoo_mcp_multi.client.httpx.post", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(OdooConnectionError, match="Connection error"):
            client._post(f"{URL}/json/2/res.partner/read", {})


def test_json2_execute_kw_401_with_non_json_body():
    client = _json2_client()
    with patch.object(client, "_post", return_value=_response(401, text="denied")):
        with pytest.raises(OdooAuthenticationError, match="denied"):
            client.execute_kw("res.partner", "read", [[1]], {})


def test_json2_execute_kw_500_with_non_json_body():
    client = _json2_client()
    with patch.object(client, "_post", return_value=_response(500, text="server exploded")):
        with pytest.raises(OdooExecutionError, match="server exploded"):
            client.execute_kw("res.partner", "read", [[1]], {})


# ---------------------------------------------------------------------------
# XmlRpcClient error branches
# ---------------------------------------------------------------------------


def test_xmlrpc_http_transport_applies_timeout():
    client = _xmlrpc_client(url="http://odoo.test")
    transport = client._get_transport()
    assert not isinstance(transport, xmlrpc.client.SafeTransport)
    connection = transport.make_connection("odoo.test")
    assert connection.timeout == client.timeout


def _xmlrpc_with_auth_error(side_effect):
    client = _xmlrpc_client()
    common = MagicMock()
    common.authenticate.side_effect = side_effect
    return client, patch.object(client, "_get_common", return_value=common)


def test_xmlrpc_authenticate_timeout():
    client, ctx = _xmlrpc_with_auth_error(socket.timeout("slow"))
    with ctx, pytest.raises(OdooConnectionError, match="timed out"):
        client._authenticate_raw()


def test_xmlrpc_authenticate_connection_refused():
    client, ctx = _xmlrpc_with_auth_error(ConnectionRefusedError("refused"))
    with ctx, pytest.raises(OdooConnectionError, match="refused"):
        client._authenticate_raw()


def test_xmlrpc_authenticate_fault_maps_to_auth_error():
    client, ctx = _xmlrpc_with_auth_error(xmlrpc.client.Fault(1, "Access Denied"))
    with ctx, pytest.raises(OdooAuthenticationError, match="Access Denied"):
        client._authenticate_raw()


def test_xmlrpc_authenticate_generic_error_maps_to_connection_error():
    client, ctx = _xmlrpc_with_auth_error(ValueError("odd failure"))
    with ctx, pytest.raises(OdooConnectionError, match="odd failure"):
        client._authenticate_raw()


def test_xmlrpc_authenticate_with_verification_disabled():
    client = _xmlrpc_client(verify=False)
    with patch.object(client, "_authenticate_raw", return_value=7):
        assert client.authenticate() == 7


def test_xmlrpc_authenticate_rejects_falsy_uid():
    client = _xmlrpc_client()
    with patch.object(client, "_authenticate_raw", return_value=False):
        with pytest.raises(OdooAuthenticationError, match="Authentication failed"):
            client.authenticate()


def _xmlrpc_with_exec_error(side_effect):
    client = _xmlrpc_client()
    obj = MagicMock()
    obj.execute_kw.side_effect = side_effect
    return client, patch.object(client, "_get_object", return_value=obj)


def test_xmlrpc_execute_timeout():
    client, ctx = _xmlrpc_with_exec_error(socket.timeout("slow"))
    with ctx, pytest.raises(OdooExecutionError, match="timed out"):
        client._execute_kw_raw(1, "res.partner", "read", [[1]], {})


def test_xmlrpc_execute_fault_missing_method():
    client, ctx = _xmlrpc_with_exec_error(xmlrpc.client.Fault(1, "'res.partner' object has no attribute 'foo'"))
    with ctx, pytest.raises(OdooMethodNotFoundError, match="foo"):
        client._execute_kw_raw(1, "res.partner", "foo", [], {})


def test_xmlrpc_execute_fault_generic():
    client, ctx = _xmlrpc_with_exec_error(xmlrpc.client.Fault(1, "ValidationError: bad vals"))
    with ctx, pytest.raises(OdooExecutionError, match="bad vals"):
        client._execute_kw_raw(1, "res.partner", "write", [[1], {}], {})


def test_xmlrpc_execute_generic_error():
    client, ctx = _xmlrpc_with_exec_error(ValueError("odd failure"))
    with ctx, pytest.raises(OdooExecutionError, match="odd failure"):
        client._execute_kw_raw(1, "res.partner", "read", [[1]], {})


def test_xmlrpc_execute_kw_with_verification_disabled():
    client = _xmlrpc_client(verify=False)
    client._uid = 1
    with patch.object(client, "_execute_kw_raw", return_value="ok"):
        assert client.execute_kw("res.partner", "read", [[1]], {}) == "ok"

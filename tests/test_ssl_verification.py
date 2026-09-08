"""Tests for SSL verification: X.509 exception checking and fail-closed behaviour on every transport."""

from __future__ import annotations

import ssl
import threading
from unittest.mock import MagicMock, patch

import httpx
import pytest

from odoo_mcp_multi.client import (
    Json2Client,
    JsonRpcClient,
    XmlRpcClient,
    is_ssl_verification_error,
)
from odoo_mcp_multi.config import OdooProfile
from odoo_mcp_multi.exceptions import OdooSSLVerificationError
from odoo_mcp_multi.operations import _with_warning


def _ssl_connect_error(url: str) -> httpx.ConnectError:
    """Build the httpx error a server with an untrusted certificate raises."""
    return httpx.ConnectError(
        "SSL certificate verification failed",
        request=httpx.Request("POST", url),
    )


def _raise_fresh_ssl_error(*_args, **_kwargs):
    """Raise a new SSL exception per call.

    Reusing one instance is what makes a retry chain it to itself (``__context__`` back to the
    error that wrapped it), and walking that cycle hangs instead of failing. A fresh instance
    keeps a regression here a failed assertion rather than a CI timeout.
    """
    raise Exception("SSL: CERTIFICATE_VERIFY_FAILED")


def test_is_ssl_verification_error_direct():
    """Verify that is_ssl_verification_error identifies standard SSL cert errors."""
    # Standard SSL verification error
    err = ssl.SSLCertVerificationError(1, "certificate verify failed: self signed certificate")
    assert is_ssl_verification_error(err) is True

    # Generic SSLError with verification failure reason
    err2 = ssl.SSLError("CERTIFICATE_VERIFY_FAILED")
    setattr(err2, "reason", "CERTIFICATE_VERIFY_FAILED")
    assert is_ssl_verification_error(err2) is True

    # Generic exception with keyword in string representation
    err3 = Exception("SSL: CERTIFICATE_VERIFY_FAILED: CA basic constraints not critical")
    assert is_ssl_verification_error(err3) is True

    # Non-SSL exception
    assert is_ssl_verification_error(ValueError("Invalid argument")) is False


def test_is_ssl_verification_error_survives_a_cyclic_chain():
    """A chain that loops back on itself terminates instead of spinning forever.

    Raising one exception instance twice, the second time inside the handler that already wrapped
    it, links ``__context__`` back to the wrapper whose ``__cause__`` is that same instance. The
    walk is run in a thread so a regression is a failed assertion, not a hung suite.
    """
    err = Exception("SSL: CERTIFICATE_VERIFY_FAILED")
    wrapper = OdooSSLVerificationError("wrapped")
    err.__context__ = wrapper
    wrapper.__cause__ = err

    result: list[bool] = []
    walker = threading.Thread(target=lambda: result.append(is_ssl_verification_error(err)), daemon=True)
    walker.start()
    walker.join(timeout=5)

    assert result == [True], "is_ssl_verification_error did not terminate on a cyclic exception chain"


def test_json2_client_ssl_fails_closed(httpx_mock):
    """Json2Client propagates the TLS error instead of retrying without verification."""
    client = Json2Client(
        url="https://ssl-error.example.com",
        database="db",
        api_key="key",
        verify=True,
    )

    url = "https://ssl-error.example.com/json/2/res.partner/search_read"
    httpx_mock.add_exception(_ssl_connect_error(url), url=url)

    with pytest.raises(OdooSSLVerificationError) as excinfo:
        client.execute_kw("res.partner", "search_read", args=[[]], kwargs={})

    assert client.verify is True
    # A single attempt: no silent retry over an unverified connection.
    assert len(httpx_mock.get_requests()) == 1
    assert client.last_warning is None
    assert "--no-verify" in str(excinfo.value)


def test_json_rpc_client_ssl_fails_closed(httpx_mock):
    """JsonRpcClient propagates the TLS error instead of retrying without verification."""
    client = JsonRpcClient(
        url="https://ssl-error.example.com",
        database="db",
        user="user",
        password="pwd",
        verify=True,
    )

    url = "https://ssl-error.example.com/jsonrpc"
    httpx_mock.add_exception(_ssl_connect_error(url), url=url)

    with pytest.raises(OdooSSLVerificationError) as excinfo:
        client.authenticate()

    assert client.verify is True
    assert len(httpx_mock.get_requests()) == 1
    assert client.last_warning is None
    assert "--no-verify" in str(excinfo.value)


@patch("xmlrpc.client.ServerProxy")
def test_xml_rpc_client_ssl_fails_closed(mock_proxy_class):
    """XmlRpcClient.authenticate propagates the TLS error instead of retrying without verification."""
    client = XmlRpcClient(
        url="https://ssl-error.example.com",
        database="db",
        user="user",
        password="pwd",
        verify=True,
    )

    mock_proxy = MagicMock()
    mock_proxy.authenticate.side_effect = _raise_fresh_ssl_error
    mock_proxy_class.return_value = mock_proxy

    with pytest.raises(OdooSSLVerificationError) as excinfo:
        client.authenticate()

    assert client.verify is True
    assert mock_proxy.authenticate.call_count == 1
    assert client.last_warning is None
    assert "--no-verify" in str(excinfo.value)


@patch("xmlrpc.client.ServerProxy")
def test_xml_rpc_client_execute_kw_ssl_fails_closed(mock_proxy_class):
    """XmlRpcClient.execute_kw propagates the TLS error instead of retrying without verification.

    ``_uid`` is set explicitly to bypass authentication, isolating the execute_kw path.
    """
    client = XmlRpcClient(
        url="https://ssl-error.example.com",
        database="db",
        user="user",
        password="pwd",
        verify=True,
    )
    client._uid = 100

    mock_proxy = MagicMock()
    mock_proxy.execute_kw.side_effect = _raise_fresh_ssl_error
    mock_proxy_class.return_value = mock_proxy

    with pytest.raises(OdooSSLVerificationError) as excinfo:
        client.execute_kw("res.partner", "search_read", args=[[]], kwargs={})

    assert client.verify is True
    assert mock_proxy.execute_kw.call_count == 1
    assert client.last_warning is None
    assert "--no-verify" in str(excinfo.value)


def test_json2_client_insecure_opt_in_is_honoured(httpx_mock):
    """An explicit verify=False still reaches the server over an unverified connection."""
    client = Json2Client(
        url="https://self-signed.example.com",
        database="db",
        api_key="key",
        verify=False,
    )

    httpx_mock.add_response(
        method="POST",
        url="https://self-signed.example.com/json/2/res.partner/search_read",
        json={"result": [{"id": 1, "name": "Partner"}]},
    )

    res = client.execute_kw("res.partner", "search_read", args=[[]], kwargs={})

    assert res == {"result": [{"id": 1, "name": "Partner"}]}
    assert client.verify is False


def test_json_rpc_client_insecure_opt_in_is_honoured(httpx_mock):
    """An explicit verify=False still reaches the server over an unverified connection."""
    client = JsonRpcClient(
        url="https://self-signed.example.com",
        database="db",
        user="user",
        password="pwd",
        verify=False,
    )

    httpx_mock.add_response(
        method="POST",
        url="https://self-signed.example.com/jsonrpc",
        json={"result": 42},
    )

    assert client.authenticate() == 42
    assert client.verify is False


@patch("xmlrpc.client.ServerProxy")
def test_xml_rpc_client_insecure_opt_in_uses_unverified_context(mock_proxy_class):
    """An explicit verify=False builds the transport with an unverified SSL context."""
    client = XmlRpcClient(
        url="https://self-signed.example.com",
        database="db",
        user="user",
        password="pwd",
        verify=False,
    )

    mock_proxy = MagicMock()
    mock_proxy.authenticate.return_value = 100
    mock_proxy_class.return_value = mock_proxy

    assert client.authenticate() == 100
    assert client._get_transport().context.verify_mode is ssl.CERT_NONE


def test_operations_warning_injection():
    """Verify that _with_warning injects the last_warning value into results."""
    mock_client = MagicMock()
    mock_client.last_warning = "Test warning"

    res = {"success": True, "data": []}
    wrapped = _with_warning(res, mock_client)

    assert wrapped["warning"] == "Test warning"
    assert wrapped["success"] is True


def test_profile_configuration():
    """Verify that OdooProfile handles explicit verify option correctly."""
    p = OdooProfile(
        name="test",
        url="https://test.com",
        database="db",
        api_key="key",
        verify=False,
    )
    assert p.verify is False

    # Check serialization
    d = p.to_dict()
    assert d["verify"] is False

    # Check deserialization
    p2 = OdooProfile.from_dict(d)
    assert p2.verify is False

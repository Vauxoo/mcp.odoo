"""Tests for SSL verification options, X.509 exception checking, and self-healing fallback retry logic."""

from __future__ import annotations

import ssl
from unittest.mock import MagicMock, patch

import httpx

from odoo_mcp_multi.client import (
    Json2Client,
    JsonRpcClient,
    XmlRpcClient,
    is_ssl_verification_error,
)
from odoo_mcp_multi.config import OdooProfile
from odoo_mcp_multi.operations import _with_warning


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


def test_json2_client_ssl_fallback(httpx_mock):
    """Json2Client automatically retries with verify=False on SSL validation error."""
    client = Json2Client(
        url="https://ssl-error.example.com",
        database="db",
        api_key="key",
        verify=True,
    )

    # First attempt raises SSL ConnectError, second attempt succeeds
    httpx_mock.add_exception(
        httpx.ConnectError(
            "SSL certificate verification failed",
            request=httpx.Request("POST", "https://ssl-error.example.com"),
        ),
        url="https://ssl-error.example.com/json/2/res.partner/search_read",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://ssl-error.example.com/json/2/res.partner/search_read",
        json={"result": [{"id": 1, "name": "Partner"}]},
    )

    # Execute
    res = client.execute_kw("res.partner", "search_read", args=[[]], kwargs={})

    # Assertions
    assert res == {"result": [{"id": 1, "name": "Partner"}]}
    assert client.verify is False
    assert client.last_warning is not None
    assert "SSL verification" in client.last_warning


def test_json_rpc_client_ssl_fallback(httpx_mock):
    """JsonRpcClient automatically retries with verify=False on SSL validation error."""
    client = JsonRpcClient(
        url="https://ssl-error.example.com",
        database="db",
        user="user",
        password="pwd",
        verify=True,
    )

    # First attempt raises SSL ConnectError, second attempt succeeds
    httpx_mock.add_exception(
        httpx.ConnectError(
            "SSL certificate verification failed",
            request=httpx.Request("POST", "https://ssl-error.example.com"),
        ),
        url="https://ssl-error.example.com/jsonrpc",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://ssl-error.example.com/jsonrpc",
        json={"result": 42},  # uid
    )

    # Mock common.authenticate
    uid = client.authenticate()

    # Assertions
    assert uid == 42
    assert client.verify is False
    assert client.last_warning is not None
    assert "SSL verification" in client.last_warning


@patch("xmlrpc.client.ServerProxy")
def test_xml_rpc_client_ssl_fallback(mock_proxy_class):
    """XmlRpcClient automatically retries with verify=False on SSL validation error."""
    client = XmlRpcClient(
        url="https://ssl-error.example.com",
        database="db",
        user="user",
        password="pwd",
        verify=True,
    )

    # Create mock instances for ServerProxy
    mock_proxy_fail = MagicMock()
    # Raise custom exception that simulates an SSL validation error
    mock_proxy_fail.authenticate.side_effect = Exception("SSL: CERTIFICATE_VERIFY_FAILED")

    mock_proxy_success = MagicMock()
    mock_proxy_success.authenticate.return_value = 100

    # Side effect returns the failing proxy first, then the success proxy on retry
    mock_proxy_class.side_effect = [mock_proxy_fail, mock_proxy_success]

    # Execute
    uid = client.authenticate()

    # Assertions
    assert uid == 100
    assert client.verify is False
    assert client.last_warning is not None
    assert "SSL verification" in client.last_warning


@patch("xmlrpc.client.ServerProxy")
def test_xml_rpc_client_execute_kw_ssl_fallback(mock_proxy_class):
    """Verify that execute_kw triggers SSL fallback to unverified context when verification fails.

    We set _uid explicitly to bypass authentication calls, isolating the validation logic
    of execute_kw. We use ServerProxy side_effect to return a failing proxy first to trigger
    fallback, then a succeeding one to verify the successful recovery path.
    """
    client = XmlRpcClient(
        url="https://ssl-error.example.com",
        database="db",
        user="user",
        password="pwd",
        verify=True,
    )
    client._uid = 100

    mock_proxy_fail = MagicMock()
    mock_proxy_fail.execute_kw.side_effect = Exception("SSL: CERTIFICATE_VERIFY_FAILED")

    mock_proxy_success = MagicMock()
    mock_proxy_success.execute_kw.return_value = [{"id": 1, "name": "Partner"}]

    mock_proxy_class.side_effect = [mock_proxy_fail, mock_proxy_success]

    res = client.execute_kw("res.partner", "search_read", args=[[]], kwargs={})

    assert res == [{"id": 1, "name": "Partner"}]
    assert client.verify is False
    assert client.last_warning is not None
    assert "SSL verification" in client.last_warning


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

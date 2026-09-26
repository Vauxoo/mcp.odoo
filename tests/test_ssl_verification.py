"""Tests for SSL verification: X.509 exception checking and fail-closed behaviour on every transport."""

from __future__ import annotations

import datetime
import ipaddress
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

import certifi
import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from odoo_mcp_multi.client import (
    Json2Client,
    JsonRpcClient,
    XmlRpcClient,
    is_ssl_verification_error,
    ssl_verification_error,
)
from odoo_mcp_multi.config import OdooProfile, build_ssl_verify
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


# ---------------------------------------------------------------------------
# Trust settings: ca_bundle and ssl_strict
# ---------------------------------------------------------------------------


def _issue_chain(tmp_path, ca_constraints_critical: bool = True):
    """Write a CA and a 127.0.0.1 server certificate signed by it; return (ca.pem, cert.pem, key.pem).

    Everything else VERIFY_X509_STRICT checks (key identifiers, key usage, EKU) is issued
    correctly, so the ``basicConstraints`` criticality is the only thing that can trip it.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "odoo-mcp test CA")])
    ca_ski = x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key())
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=ca_constraints_critical)
        .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
        .add_extension(ca_ski, critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ca_ski), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ca_ski), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem, cert_pem, key_pem = tmp_path / "ca.pem", tmp_path / "cert.pem", tmp_path / "key.pem"
    ca_pem.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_pem.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return str(ca_pem), str(cert_pem), str(key_pem)


class _JsonRpcHandler(BaseHTTPRequestHandler):
    """Answers every POST as the JSON-RPC ``authenticate`` call, with uid 7."""

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        body = b'{"jsonrpc": "2.0", "id": 1, "result": 7}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class _XmlRpcHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ("/xmlrpc/2/common",)

    def log_message(self, *_args):
        pass


class _TlsServer(ThreadingHTTPServer, SimpleXMLRPCServer):
    pass


HANDLERS = {JsonRpcClient: _JsonRpcHandler, XmlRpcClient: _XmlRpcHandler}


@pytest.fixture
def ca_constraints_critical():
    """An RFC 5280 compliant CA; parametrize to False for one whose basicConstraints is not critical."""
    return True


@pytest.fixture
def tls_odoo(tmp_path, client_class, ca_constraints_critical):
    """An HTTPS server on 127.0.0.1 speaking ``client_class``'s protocol, whose ``authenticate`` returns 7."""
    ca_pem, cert_pem, key_pem = _issue_chain(tmp_path, ca_constraints_critical)
    server = _TlsServer(("127.0.0.1", 0), requestHandler=HANDLERS[client_class], logRequests=False)
    server.register_function(lambda *_args: 7, "authenticate")
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_pem, key_pem)
    server.socket = server_context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"https://127.0.0.1:{server.server_address[1]}", ca_pem
    server.shutdown()
    server.server_close()


def _authenticate(client_class, url: str, verify) -> int:
    client = client_class(url=url, database="db", user="admin", password="pwd", verify=verify)
    return client.authenticate()


def _patch_default_flags(monkeypatch, adjust):
    """Make ``ssl.create_default_context`` return a context whose verify_flags ``adjust`` rewrote."""
    create_default_context = ssl.create_default_context

    def create_context(*args, **kwargs):
        context = create_default_context(*args, **kwargs)
        context.verify_flags = adjust(context.verify_flags)
        return context

    monkeypatch.setattr(ssl, "create_default_context", create_context)


@pytest.fixture
def strict_by_default(monkeypatch):
    """The default context sets VERIFY_X509_STRICT, as Python 3.13+ does, whatever Python runs the test."""
    _patch_default_flags(monkeypatch, lambda flags: flags | ssl.VERIFY_X509_STRICT)


@pytest.fixture
def lenient_by_default(monkeypatch):
    """The default context leaves VERIFY_X509_STRICT off, as Python 3.10-3.12 do, whatever Python runs the test."""
    _patch_default_flags(monkeypatch, lambda flags: flags & ~ssl.VERIFY_X509_STRICT)


@pytest.mark.parametrize("client_class", [JsonRpcClient, XmlRpcClient])
def test_ca_bundle_trusts_a_private_ca(tls_odoo, client_class):
    """The default trust store refuses the private CA; the profile's ca_bundle makes it verify."""
    url, ca_pem = tls_odoo
    with pytest.raises(OdooSSLVerificationError):
        _authenticate(client_class, url, build_ssl_verify(True))
    assert _authenticate(client_class, url, build_ssl_verify(True, ca_bundle=ca_pem)) == 7


@pytest.mark.parametrize("ca_constraints_critical", [False])
@pytest.mark.parametrize("client_class", [JsonRpcClient, XmlRpcClient])
def test_ssl_strict_off_accepts_non_critical_basic_constraints(tls_odoo, client_class, strict_by_default):
    """On a strict Python the CA fails with the default ssl_strict, and verifies once it is relaxed."""
    url, ca_pem = tls_odoo
    with pytest.raises(OdooSSLVerificationError, match="not marked critical"):
        _authenticate(client_class, url, build_ssl_verify(True, ca_bundle=ca_pem))
    assert _authenticate(client_class, url, build_ssl_verify(True, ca_bundle=ca_pem, ssl_strict=False)) == 7


@pytest.mark.parametrize("ca_constraints_critical", [False])
@pytest.mark.parametrize("client_class", [JsonRpcClient, XmlRpcClient])
def test_lenient_python_accepts_non_critical_basic_constraints(tls_odoo, client_class, lenient_by_default):
    """On a Python without STRICT the same CA verifies untouched: ssl_strict adds no check of its own."""
    url, ca_pem = tls_odoo
    assert _authenticate(client_class, url, build_ssl_verify(True, ca_bundle=ca_pem)) == 7


def test_ssl_strict_keeps_the_python_default_flags():
    """ssl_strict=True means "what this Python does": the context carries exactly its default flags.

    Holds on every version, so the two tests above, which pin each default, also describe the
    Python running the suite.
    """
    context = build_ssl_verify(True, ca_bundle=certifi.where())
    assert context.verify_flags == ssl.create_default_context().verify_flags


def test_build_ssl_verify_keeps_plain_values_by_default():
    """Profiles that set neither knob pass a bool, so each transport keeps its own trust store."""
    assert build_ssl_verify(True) is True
    assert build_ssl_verify(False) is False


def test_build_ssl_verify_opt_out_wins_over_trust_settings(tmp_path):
    """--no-verify is never silently overridden by a stale bundle or strict setting."""
    assert build_ssl_verify(False, ca_bundle=str(tmp_path / "missing.pem"), ssl_strict=False) is False


def test_build_ssl_verify_relaxed_context_still_verifies():
    """ssl_strict=False drops only VERIFY_X509_STRICT: chain and hostname are still checked."""
    context = build_ssl_verify(True, ssl_strict=False)
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert not context.verify_flags & ssl.VERIFY_X509_STRICT


def test_profile_round_trips_trust_settings():
    """ca_bundle and ssl_strict persist, and are omitted from profiles.json while at their defaults."""
    profile = OdooProfile(name="p", url="https://x", database="db", user="u", password="pwd")
    assert "ca_bundle" not in profile.to_dict()
    assert "ssl_strict" not in profile.to_dict()
    assert profile.ssl_verify() is True

    tuned = profile.model_copy(update={"ca_bundle": "/etc/ca.pem", "ssl_strict": False})
    restored = OdooProfile.from_dict(tuned.to_dict())
    assert restored.ca_bundle == "/etc/ca.pem"
    assert restored.ssl_strict is False


def test_ssl_error_hint_offers_trust_before_opt_out():
    """The message an agent reads points at --ca-bundle and says --no-verify is a person's call."""
    message = str(ssl_verification_error(Exception("certificate verify failed")))
    assert message.index("--ca-bundle") < message.index("--no-verify")
    assert "never one to apply automatically" in message


@pytest.mark.parametrize("timeout", [None, 60])
def test_get_client_passes_the_profile_trust_settings(monkeypatch, timeout):
    """``serve`` sets a default timeout, which takes its own create_client call;
    both calls must hand the transports the profile's CA bundle and strict mode."""
    import ssl

    import certifi

    from odoo_mcp_multi import operations

    profile = OdooProfile(
        name="p", url="https://odoo.example.com", database="db", user="u", password="x", ca_bundle=certifi.where()
    )
    monkeypatch.setattr(operations, "resolve_active_profile", lambda name=None: profile)
    monkeypatch.setattr(operations, "_default_timeout", timeout)
    seen = {}
    monkeypatch.setattr(operations, "create_client", lambda **kw: seen.update(kw))

    operations._get_client()

    assert isinstance(seen["verify"], ssl.SSLContext)

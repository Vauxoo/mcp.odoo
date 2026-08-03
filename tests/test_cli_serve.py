"""`odoo-mcp serve` must refuse to start in configurations that would fail.

Every check here maps to a specific way a remote connector breaks in the
field, and each one is far cheaper to hit as a startup error than as an
opaque client-side failure after a deploy.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from odoo_mcp_multi.cli import main
from odoo_mcp_multi.http.settings import ConfigError, HttpServeConfig


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def state_paths(tmp_path):
    return ["--state-db", str(tmp_path / "s.db"), "--secret-key-file", str(tmp_path / "k.key")]


# -- configuration derivation ----------------------------------------------


def test_public_url_drives_issuer_and_resource():
    config = HttpServeConfig(public_url="https://odoo-mcp.me1980.com/mcp")
    assert config.issuer_url == "https://odoo-mcp.me1980.com"
    assert config.resource_url == "https://odoo-mcp.me1980.com/mcp"
    assert config.protected_resource_path == "/.well-known/oauth-protected-resource/mcp"
    assert config.login_url == "https://odoo-mcp.me1980.com/odoo/login"


def test_a_non_default_path_is_carried_through():
    config = HttpServeConfig(path="/odoo/mcp", public_url="https://h.example.com/odoo/mcp")
    assert config.resource_url == "https://h.example.com/odoo/mcp"
    assert config.protected_resource_path == "/.well-known/oauth-protected-resource/odoo/mcp"


def test_path_must_match_public_url():
    """The single most common reason a connector is rejected."""
    with pytest.raises(ConfigError) as excinfo:
        HttpServeConfig(path="/", public_url="https://h.example.com/mcp")
    assert "--path" in str(excinfo.value)


def test_public_url_without_a_path_is_rejected_when_path_is_custom():
    with pytest.raises(ConfigError):
        HttpServeConfig(path="/odoo/mcp", public_url="https://h.example.com")


def test_a_public_host_must_use_https():
    with pytest.raises(ConfigError) as excinfo:
        HttpServeConfig(public_url="http://public.example.com/mcp")
    assert "https" in str(excinfo.value)


def test_loopback_may_use_http():
    config = HttpServeConfig(public_url="http://127.0.0.1:5010/mcp")
    assert config.resource_url == "http://127.0.0.1:5010/mcp"


def test_auth_requires_a_public_url():
    with pytest.raises(ConfigError) as excinfo:
        HttpServeConfig(public_url=None)
    assert "--public-url" in str(excinfo.value)


def test_no_auth_refuses_a_public_bind():
    config = HttpServeConfig(host="0.0.0.0", auth_enabled=False)
    with pytest.raises(ConfigError) as excinfo:
        config.validate_runtime()
    assert "Refusing to bind" in str(excinfo.value)


def test_no_auth_may_bind_loopback():
    HttpServeConfig(host="127.0.0.1", auth_enabled=False).validate_runtime()


def test_no_auth_contradicts_an_https_public_url():
    config = HttpServeConfig(host="127.0.0.1", auth_enabled=False, public_url="https://h.example.com/mcp")
    with pytest.raises(ConfigError):
        config.validate_runtime()


# -- the CLI itself ---------------------------------------------------------


def test_serve_rejects_a_public_bind_without_auth(runner, state_paths):
    result = runner.invoke(main, ["serve", "--no-auth", "--host", "0.0.0.0", *state_paths])
    assert result.exit_code == 2
    assert "Refusing to bind" in result.output


def test_serve_rejects_a_path_mismatch(runner, state_paths):
    result = runner.invoke(main, ["serve", "--public-url", "https://h.example.com/mcp", "--path", "/", *state_paths])
    assert result.exit_code == 2
    assert "--path" in result.output


def test_the_public_hostname_survives_the_rebinding_guard():
    """FastMCP allows only loopback Hosts by default; behind a proxy the Host
    is the public name, and every request would be rejected with 421."""
    from odoo_mcp_multi.http.app import build_transport_security

    config = HttpServeConfig(public_url="https://odoo-mcp.me1980.com/mcp")
    security = build_transport_security(config)

    assert security.enable_dns_rebinding_protection is True
    assert "odoo-mcp.me1980.com" in security.allowed_hosts
    assert "https://odoo-mcp.me1980.com" in security.allowed_origins


def test_serve_binds_what_it_was_told(runner, state_paths):
    with patch("uvicorn.run") as run:
        result = runner.invoke(
            main,
            ["serve", "--public-url", "https://odoo-mcp.me1980.com/mcp", "--port", "5010", *state_paths],
        )

    assert result.exit_code == 0, result.output
    run.assert_called_once()
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["port"] == 5010
    assert "https://odoo-mcp.me1980.com/mcp" in result.output


def test_serve_warns_loudly_without_auth(runner, state_paths):
    with patch("uvicorn.run"):
        result = runner.invoke(main, ["serve", "--no-auth", *state_paths])
    assert result.exit_code == 0, result.output
    assert "authentication is disabled" in result.output


def test_http_group_is_registered(runner):
    result = runner.invoke(main, ["--help"])
    assert "serve" in result.output
    assert "http" in result.output


def test_http_grants_reports_an_empty_store(runner, state_paths):
    result = runner.invoke(main, ["http", "grants", *state_paths])
    assert result.exit_code == 0
    assert "No active grants" in result.output


def test_http_revoke_requires_a_target(runner, state_paths):
    result = runner.invoke(main, ["http", "revoke", *state_paths])
    assert result.exit_code == 1
    assert "GRANT_ID" in result.output


def test_http_purge_reports_counts(runner, state_paths):
    result = runner.invoke(main, ["http", "purge", *state_paths])
    assert result.exit_code == 0
    assert "access_tokens" in result.output

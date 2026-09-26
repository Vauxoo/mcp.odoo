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


@pytest.mark.parametrize("host", ["0.0.0.0", "127.1", "::ffff:127.0.0.1", "LOCALHOST", "127.0.0.1.nip.io", ""])
def test_local_auth_fails_closed_on_anything_but_an_exact_loopback_name(host):
    with pytest.raises(ConfigError):
        HttpServeConfig(host=host, auth_enabled=False).validate_runtime()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]"])
def test_local_auth_accepts_the_exact_loopback_names(host):
    HttpServeConfig(host=host, auth_enabled=False).validate_runtime()


def test_local_auth_only_trusts_loopback_hosts_and_origins():
    """CLI clients send no Origin, so any Origin means a browser page: refuse it."""
    from odoo_mcp_multi.http.app import build_transport_security

    security = build_transport_security(HttpServeConfig(host="127.0.0.1", auth_enabled=False))

    assert security.enable_dns_rebinding_protection is True
    assert set(security.allowed_hosts) == {"127.0.0.1:*", "localhost:*", "[::1]:*"}
    assert security.allowed_origins == []


def test_no_auth_contradicts_an_https_public_url():
    config = HttpServeConfig(host="127.0.0.1", auth_enabled=False, public_url="https://h.example.com/mcp")
    with pytest.raises(ConfigError):
        config.validate_runtime()


# -- the CLI itself ---------------------------------------------------------


def test_serve_rejects_a_public_bind_without_auth(runner, state_paths):
    result = runner.invoke(main, ["serve", "--auth", "local", "--host", "0.0.0.0", *state_paths])
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


async def test_a_proxied_host_would_be_rejected_without_the_explicit_policy(http_config, auth_store):
    """Regression guard for the failure this policy exists to prevent.

    Built against FastMCP's default, an authenticated request arriving with
    the public Host header — exactly what a reverse proxy sends — is answered
    with 421 Misdirected Request before it reaches any handler.
    """
    import httpx

    from odoo_mcp_multi.http import app as app_module
    from tests.conftest import PUBLIC_HOST, _Lifespan

    credential_id = auth_store.put_credential(
        {
            "name": "oauth:db",
            "url": "https://odoo.example.com",
            "database": "db",
            "user": "someone",
            "api_key": "k",
            "protocol": "json2s",
        },
        uid=1,
    )
    grant_id = auth_store.create_grant(
        client_id="c",
        credential_id=credential_id,
        scopes=["odoo:read", "odoo:write"],
        resource=http_config.resource_url,
    )
    token, _ = auth_store.put_access_token(grant_id, ttl=3600)

    async def initialize(app):
        async with _Lifespan(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=f"https://{PUBLIC_HOST}"
            ) as scoped:
                return await scoped.post(
                    "/mcp",
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "Authorization": f"Bearer {token}",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "t", "version": "1"},
                        },
                    },
                )

    configured = await initialize(app_module.build_http_app(http_config))
    assert configured.status_code == 200, configured.text

    with patch.object(app_module, "build_transport_security", return_value=None):
        defaulted = await initialize(app_module.build_http_app(http_config))
    assert defaulted.status_code == 421, "the default policy must be the one that rejects it"


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


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Keep the local token out of the real ~/.config/odoo-mcp."""
    monkeypatch.setattr("odoo_mcp_multi.http.settings._default_config_dir", lambda: tmp_path)
    return tmp_path


def test_serve_local_tells_how_to_register_the_client(runner, state_paths, config_dir):
    with patch("uvicorn.run"), patch("odoo_mcp_multi.cli.get_profile", return_value=None):
        result = runner.invoke(main, ["serve", "--auth", "local", *state_paths])
    assert result.exit_code == 0, result.output
    token_file = config_dir / "local-token"
    assert str(token_file) in result.output
    assert f'--header "Authorization: Bearer $(cat {token_file})"' in result.output
    assert token_file.read_text().strip() not in result.output, "the token itself must never be printed"


def test_serve_local_refuses_a_token_file_others_can_read(runner, state_paths, config_dir):
    token_file = config_dir / "local-token"
    token_file.write_text("t\n")
    token_file.chmod(0o644)
    with patch("uvicorn.run") as run, patch("odoo_mcp_multi.cli.get_profile", return_value=None):
        result = runner.invoke(main, ["serve", "--auth", "local", *state_paths])
    assert result.exit_code == 2
    assert "chmod 600" in result.output
    run.assert_not_called()


def test_rotate_token_requires_local_auth(runner, state_paths):
    result = runner.invoke(
        main, ["serve", "--public-url", "https://h.example.com/mcp", "--rotate-token", *state_paths]
    )
    assert result.exit_code == 2
    assert "--auth local" in result.output


def test_local_token_is_created_private_and_reused(tmp_path):
    from odoo_mcp_multi.http.settings import load_local_token

    path = tmp_path / "local-token"
    first = load_local_token(path)
    assert len(first) >= 40
    assert path.stat().st_mode & 0o777 == 0o600
    assert load_local_token(path) == first
    rotated = load_local_token(path, rotate=True)
    assert rotated != first
    assert load_local_token(path) == rotated


def test_serve_rejects_a_profile_with_oauth(runner, state_paths):
    result = runner.invoke(
        main, ["serve", "--public-url", "https://h.example.com/mcp", "--profile", "prod", *state_paths]
    )
    assert result.exit_code == 2
    assert "--auth local" in result.output


def test_serve_local_rejects_an_unknown_profile(runner, state_paths):
    with patch("uvicorn.run") as run, patch("odoo_mcp_multi.cli.get_profile", return_value=None):
        result = runner.invoke(main, ["serve", "--auth", "local", "--profile", "nope", *state_paths])
    assert result.exit_code == 1
    assert "not found" in result.output
    run.assert_not_called()


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

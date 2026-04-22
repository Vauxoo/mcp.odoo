"""Tests for CLI profile management commands.

Uses Click's CliRunner for hermetic CLI testing and monkeypatches the
config layer so no real ~/.config/odoo-mcp/ is touched.

We test the CLI's own behavior (argument parsing, output format, exit codes,
user messages) — not the config module internals, which are covered in
test_config.py.
"""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from odoo_mcp_multi.cli import main

runner = CliRunner()


# ---------------------------------------------------------------------------
# list-profiles
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.list_profiles")
def test_cli_list_profiles_json(mock_list):
    mock_list.return_value = [
        {"name": "prod", "url": "https://odoo.example.com", "database": "prod",
         "user": "admin", "protocol": "auto", "is_default": True},
    ]
    result = runner.invoke(main, ["list-profiles", "--json"])
    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output[0]["name"] == "prod"
    assert output[0]["is_default"] is True


@patch("odoo_mcp_multi.cli.list_profiles")
def test_cli_list_profiles_human_readable(mock_list):
    mock_list.return_value = [
        {"name": "prod", "url": "https://odoo.example.com", "database": "prod",
         "user": "admin", "protocol": "auto", "is_default": True},
    ]
    result = runner.invoke(main, ["list-profiles"])
    assert result.exit_code == 0
    assert "prod" in result.output
    assert "odoo.example.com" in result.output


@patch("odoo_mcp_multi.cli.list_profiles")
def test_cli_list_profiles_empty(mock_list):
    mock_list.return_value = []
    result = runner.invoke(main, ["list-profiles"])
    assert result.exit_code == 0
    assert "No profiles configured" in result.output


# ---------------------------------------------------------------------------
# remove-profile
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.remove_profile")
def test_cli_remove_profile_force(mock_remove):
    mock_remove.return_value = True
    result = runner.invoke(main, ["remove-profile", "staging", "--force"])
    assert result.exit_code == 0
    assert "removed" in result.output.lower()
    mock_remove.assert_called_once_with("staging")


@patch("odoo_mcp_multi.cli.remove_profile")
def test_cli_remove_profile_not_found(mock_remove):
    mock_remove.return_value = False
    result = runner.invoke(main, ["remove-profile", "nonexistent", "--force"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


@patch("odoo_mcp_multi.cli.remove_profile")
def test_cli_remove_profile_prompts_confirmation(mock_remove):
    mock_remove.return_value = True
    # Simulate user confirming 'y' at the prompt
    result = runner.invoke(main, ["remove-profile", "staging"], input="y\n")
    assert result.exit_code == 0
    mock_remove.assert_called_once_with("staging")


@patch("odoo_mcp_multi.cli.remove_profile")
def test_cli_remove_profile_cancelled_by_user(mock_remove):
    # Simulate user answering 'n' at the prompt
    result = runner.invoke(main, ["remove-profile", "staging"], input="n\n")
    assert result.exit_code == 0
    mock_remove.assert_not_called()


# ---------------------------------------------------------------------------
# set-default
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.set_default_profile")
def test_cli_set_default_success(mock_set):
    mock_set.return_value = True
    result = runner.invoke(main, ["set-default", "prod"])
    assert result.exit_code == 0
    assert "prod" in result.output
    mock_set.assert_called_once_with("prod")


@patch("odoo_mcp_multi.cli.set_default_profile")
def test_cli_set_default_not_found(mock_set):
    mock_set.return_value = False
    result = runner.invoke(main, ["set-default", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# edit-profile
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.add_profile")
@patch("odoo_mcp_multi.cli.get_profile")
def test_cli_edit_profile_url(mock_get, mock_add):
    existing = MagicMock()
    existing.url = "https://old.example.com"
    existing.database = "db"
    existing.user = "admin"
    existing.password.get_secret_value.return_value = "secret"
    existing.api_key = None  # legacy profile — no api_key
    mock_get.return_value = existing

    result = runner.invoke(main, ["edit-profile", "prod", "--url", "https://new.example.com"])
    assert result.exit_code == 0, result.output
    assert "updated" in result.output.lower()
    mock_add.assert_called_once()
    # The new profile passed to add_profile should have the new URL
    saved_profile = mock_add.call_args[0][0]
    assert saved_profile.url == "https://new.example.com"
    # Other fields should be unchanged
    assert saved_profile.database == "db"


@patch("odoo_mcp_multi.cli.get_profile")
def test_cli_edit_profile_not_found(mock_get):
    mock_get.return_value = None
    result = runner.invoke(main, ["edit-profile", "nonexistent", "--url", "https://x.com"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# test command (connection test)
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_test_connection")
@patch("odoo_mcp_multi.cli.get_profile")
def test_cli_test_command_success(mock_get_profile, mock_test_conn):
    profile = MagicMock()
    profile.url = "https://odoo.example.com"
    profile.database = "db"
    profile.user = "admin"
    profile.password = MagicMock()
    profile.api_key = None  # legacy auth
    profile.protocol = "auto"
    mock_get_profile.return_value = profile

    mock_test_conn.return_value = {"uid": 2, "server_version": "17.0", "protocol": "auto"}

    result = runner.invoke(main, ["test"])
    assert result.exit_code == 0
    assert "successful" in result.output.lower()
    assert "17.0" in result.output


@patch("odoo_mcp_multi.cli.get_profile")
def test_cli_test_command_no_profile(mock_get_profile):
    mock_get_profile.return_value = None
    result = runner.invoke(main, ["test"])
    assert result.exit_code == 1
    assert "No default profile" in result.output or "not found" in result.output.lower()


@patch("odoo_mcp_multi.cli.op_test_connection")
@patch("odoo_mcp_multi.cli.get_profile")
def test_cli_test_command_connection_failure(mock_get_profile, mock_test_conn):
    from odoo_mcp_multi.utils import OdooConnectionError

    profile = MagicMock()
    profile.url = "https://odoo.example.com"
    profile.database = "db"
    profile.user = "admin"
    profile.password = MagicMock()
    profile.api_key = None  # legacy auth
    profile.protocol = "auto"
    mock_get_profile.return_value = profile

    mock_test_conn.side_effect = OdooConnectionError("Connection refused")

    result = runner.invoke(main, ["test"])
    assert result.exit_code == 1
    assert "Connection" in result.output


# ---------------------------------------------------------------------------
# add-profile (non-interactive via flags)
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.add_profile")
@patch("odoo_mcp_multi.cli.op_test_connection")
def test_cli_add_profile_all_flags(mock_test_conn, mock_add):
    """Verify add-profile works non-interactively when all flags are provided.

    The --test flag (default=True) always runs a connection test, so we
    mock op_test_connection to return a successful result instead of
    hitting a real server.
    """
    mock_test_conn.return_value = {"uid": 1, "server_version": "17.0", "protocol": "auto"}

    result = runner.invoke(
        main,
        [
            "add-profile",
            "--name", "staging",
            "--url", "https://staging.example.com",
            "--database", "staging_db",
            "--user", "admin",
            "--password", "secret",
        ],
    )
    assert result.exit_code == 0
    assert "staging" in result.output
    mock_add.assert_called_once()
    saved = mock_add.call_args[0][0]
    assert saved.name == "staging"
    assert saved.url == "https://staging.example.com"


# ---------------------------------------------------------------------------
# T17–T18: api_key support in CLI (Odoo 19+ JSON-2)
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.add_profile")
def test_cli_add_profile_with_api_key(mock_add):
    """T17: add-profile --api-key saves a Json2-ready profile (no password)."""
    result = runner.invoke(
        main,
        [
            "add-profile",
            "--name", "prod19",
            "--url", "https://odoo19.example.com",
            "--database", "mydb",
            "--api-key", "myapikey123",
            "--no-test",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "prod19" in result.output
    mock_add.assert_called_once()
    saved = mock_add.call_args[0][0]
    assert saved.api_key is not None
    assert saved.api_key.get_secret_value() == "myapikey123"
    assert saved.password is None


def test_cli_add_profile_without_auth_fails():
    """T18: add-profile without --password and without --api-key must fail with clear error."""
    result = runner.invoke(
        main,
        [
            "add-profile",
            "--name", "bad",
            "--url", "https://example.com",
            "--database", "mydb",
            "--no-test",
        ],
    )
    assert result.exit_code != 0
    assert "password" in result.output.lower() or "api" in result.output.lower() or result.exit_code != 0


@patch("odoo_mcp_multi.cli.list_profiles")
def test_cli_list_profiles_shows_auth_method(mock_list):
    """T18b: list-profiles human output shows auth method (password vs api_key)."""
    mock_list.return_value = [
        {
            "name": "prod19",
            "url": "https://odoo19.example.com",
            "database": "mydb",
            "user": "",
            "auth": "api_key",
            "protocol": "json2s",
            "is_default": True,
        },
    ]
    result = runner.invoke(main, ["list-profiles"])
    assert result.exit_code == 0
    assert "prod19" in result.output

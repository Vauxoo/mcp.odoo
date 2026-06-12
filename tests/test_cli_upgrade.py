"""Tests for the `odoo-mcp upgrade` self-update command.

Covers three installation contexts:
- Editable (pip install -e .): recommends git pull
- pipx: runs pipx upgrade
- Regular pip: runs pip install --upgrade

Also tests --force flag and failure handling.
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from odoo_mcp_multi.cli import main

runner = CliRunner()


# ---------------------------------------------------------------------------
# Installation context detection
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.subprocess.run")
def test_detect_editable_install(mock_run):
    """Detects editable install from 'Editable project location' in pip show."""
    from odoo_mcp_multi.cli import _detect_install_context

    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="Name: odoo-mcp-multi\nEditable project location: /src/odoo-mcp\n",
    )
    assert _detect_install_context() == "editable"


@patch("odoo_mcp_multi.cli.subprocess.run")
def test_detect_pipx_install(mock_run):
    """Detects pipx install from sys.executable path containing 'pipx'."""
    from odoo_mcp_multi.cli import _detect_install_context

    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="Name: odoo-mcp-multi\nVersion: 0.8.1\n",
    )
    with patch("odoo_mcp_multi.cli.sys") as mock_sys:
        mock_sys.executable = "/Users/nhomar/.local/pipx/venvs/odoo-mcp-multi/bin/python"
        assert _detect_install_context() == "pipx"


@patch("odoo_mcp_multi.cli.subprocess.run")
def test_detect_pip_install(mock_run):
    """Detects regular pip install when not editable and not pipx."""
    from odoo_mcp_multi.cli import _detect_install_context

    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="Name: odoo-mcp-multi\nVersion: 0.8.1\n",
    )
    with patch("odoo_mcp_multi.cli.sys") as mock_sys:
        mock_sys.executable = "/usr/bin/python3"
        assert _detect_install_context() == "pip"


# ---------------------------------------------------------------------------
# Editable install — warns and suggests git pull
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli._detect_install_context", return_value="editable")
def test_upgrade_editable_warns(mock_ctx):
    """Editable installs show a warning and suggest git pull."""
    result = runner.invoke(main, ["upgrade"])
    assert result.exit_code == 0
    assert "git pull" in result.output.lower()


# ---------------------------------------------------------------------------
# pipx install — runs pipx upgrade
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli._detect_install_context", return_value="pipx")
@patch("odoo_mcp_multi.cli._run_upgrade_command")
def test_upgrade_pipx(mock_run, mock_ctx):
    """pipx install runs 'pipx upgrade odoo-mcp-multi'."""
    mock_run.return_value = (0, "upgraded package odoo-mcp-multi from 0.8.0 to 0.9.0")
    result = runner.invoke(main, ["upgrade"])
    assert result.exit_code == 0
    call_args = mock_run.call_args[0][0]
    assert "pipx" in call_args
    assert "upgrade" in call_args


# ---------------------------------------------------------------------------
# Regular pip install — runs pip install --upgrade
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli._detect_install_context", return_value="pip")
@patch("odoo_mcp_multi.cli._run_upgrade_command")
def test_upgrade_pip(mock_run, mock_ctx):
    """Regular pip install runs 'pip install --upgrade odoo-mcp-multi'."""
    mock_run.return_value = (0, "Successfully installed odoo-mcp-multi-0.9.0")
    result = runner.invoke(main, ["upgrade"])
    assert result.exit_code == 0
    call_args = mock_run.call_args[0][0]
    assert "pip" in call_args
    assert "--upgrade" in call_args


# ---------------------------------------------------------------------------
# Already at latest version
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli._detect_install_context", return_value="pip")
@patch("odoo_mcp_multi.cli._run_upgrade_command")
def test_upgrade_already_latest(mock_run, mock_ctx):
    """Reports when already at latest version."""
    mock_run.return_value = (0, "Requirement already satisfied: odoo-mcp-multi")
    result = runner.invoke(main, ["upgrade"])
    assert result.exit_code == 0
    assert "already" in result.output.lower() or "latest" in result.output.lower()


# ---------------------------------------------------------------------------
# Pip failure
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli._detect_install_context", return_value="pip")
@patch("odoo_mcp_multi.cli._run_upgrade_command")
def test_upgrade_failure(mock_run, mock_ctx):
    """Exit 1 with error message when pip/pipx fails."""
    mock_run.return_value = (1, "ERROR: Could not find a version")
    result = runner.invoke(main, ["upgrade"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# --force bypasses editable check
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli._detect_install_context", return_value="editable")
@patch("odoo_mcp_multi.cli._run_upgrade_command")
def test_upgrade_force_bypasses_editable(mock_run, mock_ctx):
    """--force flag overrides the editable install warning."""
    mock_run.return_value = (0, "Successfully installed odoo-mcp-multi-0.9.0")
    result = runner.invoke(main, ["upgrade", "--force"])
    assert result.exit_code == 0
    mock_run.assert_called_once()

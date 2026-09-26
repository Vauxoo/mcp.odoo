"""Tests for the `odoo-mcp upgrade` self-update command.

Covers the installation contexts:
- Editable (pip install -e .): recommends git pull
- pipx: runs pipx upgrade
- uv tool install: runs uv tool upgrade
- uvx: nothing installed, explains how to refresh the cache
- Regular pip: runs pip install --upgrade

Also tests --force flag and failure handling.
"""

from unittest.mock import patch

from click.testing import CliRunner

from odoo_mcp_multi.cli import main

runner = CliRunner()


# ---------------------------------------------------------------------------
# Installation context detection
# ---------------------------------------------------------------------------


def _detect_in(prefix, executable="/usr/bin/python3", editable=False) -> str:
    """Run the detection as if the interpreter lived in ``prefix``."""
    from odoo_mcp_multi.cli import _detect_install_context

    with (
        patch("odoo_mcp_multi.cli.sys") as mock_sys,
        patch("odoo_mcp_multi.cli._is_editable_install", return_value=editable),
    ):
        mock_sys.prefix = str(prefix)
        mock_sys.executable = executable
        return _detect_install_context()


def _uv_venv(prefix):
    """A venv as uv creates it: cache tag, and uv's version in pyvenv.cfg."""
    prefix.mkdir(parents=True, exist_ok=True)
    (prefix / "CACHEDIR.TAG").touch()
    (prefix / "pyvenv.cfg").write_text("home = /usr/bin\nuv = 0.11.2\n", encoding="utf-8")
    return prefix


def test_detect_uv_tool_install(tmp_path):
    """`uv tool install` is recognised by its receipt; its venv has no pip to ask."""
    prefix = _uv_venv(tmp_path / "tools" / "odoo-mcp-multi")
    (prefix / "uv-receipt.toml").touch()
    assert _detect_in(prefix) == "uv-tool"


def test_detect_editable_uv_tool_install(tmp_path):
    """`uv tool install -e .` has a receipt too, but must not be upgraded from PyPI over the checkout."""
    prefix = _uv_venv(tmp_path / "tools" / "odoo-mcp-multi")
    (prefix / "uv-receipt.toml").touch()
    assert _detect_in(prefix, editable=True) == "editable"


def test_detect_uvx_run(tmp_path):
    """uvx runs from an archive-v* entry of the uv cache."""
    assert _detect_in(_uv_venv(tmp_path / "archive-v0" / "QrNLKKeBTi2a")) == "uvx"


def test_detect_editable_install_in_a_uv_venv(tmp_path):
    """An editable checkout in a uv-created venv stays 'editable', so upgrade never overwrites it."""
    assert _detect_in(_uv_venv(tmp_path / ".venv"), editable=True) == "editable"


def test_detect_uv_venv_install(tmp_path):
    """A regular install in a venv uv created is upgraded through uv, not the missing pip."""
    assert _detect_in(_uv_venv(tmp_path / ".venv")) == "uv-venv"


def test_detect_pipx_install(tmp_path):
    """Detects pipx install from sys.executable path containing 'pipx'."""
    executable = "/Users/nhomar/.local/pipx/venvs/odoo-mcp-multi/bin/python"
    assert _detect_in(tmp_path, executable=executable) == "pipx"


def test_detect_pipx_install_built_by_uv(tmp_path):
    """pipx builds its venvs with uv when uv is installed; it is still upgraded through pipx."""
    prefix = _uv_venv(tmp_path / "pipx" / "venvs" / "odoo-mcp-multi")
    assert _detect_in(prefix, executable=f"{prefix}/bin/python") == "pipx"


def test_detect_pip_install(tmp_path):
    """Detects regular pip install when not editable, not pipx and not uv."""
    assert _detect_in(tmp_path) == "pip"


@patch("odoo_mcp_multi.cli.importlib.metadata.distribution")
def test_editable_install_read_from_direct_url(mock_distribution):
    """PEP 610: an editable install records dir_info.editable in direct_url.json."""
    from odoo_mcp_multi.cli import _is_editable_install

    mock_distribution.return_value.read_text.return_value = (
        '{"url": "file:///src/odoo-mcp", "dir_info": {"editable": true}}'
    )
    assert _is_editable_install() is True


@patch("odoo_mcp_multi.cli.importlib.metadata.distribution")
def test_index_install_has_no_direct_url(mock_distribution):
    """A wheel from an index writes no direct_url.json, so it is not editable."""
    from odoo_mcp_multi.cli import _is_editable_install

    mock_distribution.return_value.read_text.return_value = None
    assert _is_editable_install() is False


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
# uv tool install — runs uv tool upgrade; uvx — nothing to upgrade
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli._detect_install_context", return_value="uv-tool")
@patch("odoo_mcp_multi.cli._run_upgrade_command")
def test_upgrade_uv_tool(mock_run, mock_ctx):
    """uv tool install runs 'uv tool upgrade odoo-mcp-multi' and reads uv's up-to-date wording."""
    mock_run.return_value = (0, "Nothing to upgrade")
    result = runner.invoke(main, ["upgrade"])
    assert result.exit_code == 0
    assert mock_run.call_args[0][0] == ["uv", "tool", "upgrade", "odoo-mcp-multi"]
    assert "already at the latest version" in result.output.lower()


@patch("odoo_mcp_multi.cli._detect_install_context", return_value="uv-venv")
@patch("odoo_mcp_multi.cli._run_upgrade_command")
def test_upgrade_uv_venv(mock_run, mock_ctx):
    """A uv-created venv is upgraded with `uv pip`, targeting this interpreter."""
    mock_run.return_value = (0, "Installed 1 package")
    result = runner.invoke(main, ["upgrade"])
    assert result.exit_code == 0
    assert mock_run.call_args[0][0][:5] == ["uv", "pip", "install", "--upgrade", "--python"]


@patch("odoo_mcp_multi.cli._detect_install_context", return_value="uvx")
@patch("odoo_mcp_multi.cli._run_upgrade_command")
def test_upgrade_uvx_explains_the_cache(mock_run, mock_ctx):
    """Under uvx there is no install to upgrade: explain @latest instead of running anything."""
    result = runner.invoke(main, ["upgrade"])
    assert result.exit_code == 0
    assert "uvx --from odoo-mcp-multi@latest" in result.output
    mock_run.assert_not_called()


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

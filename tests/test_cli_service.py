"""`odoo-mcp service`: the systemd user unit that runs `serve --auth local`.

systemctl, the platform and PATH are faked here so every case runs the same
on any interpreter and OS; the real systemd behaviour is exercised by
.gitlab/ci/service_systemd.sh in a systemd container.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from click.testing import CliRunner

from odoo_mcp_multi import __version__, service
from odoo_mcp_multi.cli import main


class FakeSystemctl:
    """Records `systemctl --user` calls and answers with a chosen exit code."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.returncode = 0
        self.stderr = ""

    def __call__(self, cmd, capture_output=True, text=True):
        self.calls.append(cmd)
        return subprocess.CompletedProcess(cmd, self.returncode, "", self.stderr)

    @property
    def verbs(self) -> list[str]:
        return [" ".join(call[2:]) for call in self.calls if call[:2] == ["systemctl", "--user"]]


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def linux(monkeypatch, tmp_path):
    """A Linux host with systemd and uvx on PATH, config dirs under tmp_path."""
    monkeypatch.setattr(service.sys, "platform", "linux")
    monkeypatch.setattr(service.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr("odoo_mcp_multi.http.settings._default_config_dir", lambda: tmp_path / "odoo-mcp")
    monkeypatch.setattr("odoo_mcp_multi.cli.get_profile", lambda name: object())
    monkeypatch.setattr(service, "_port_open", lambda host, port: True)
    monkeypatch.setattr(service.time, "sleep", lambda seconds: None)
    fake = FakeSystemctl()
    monkeypatch.setattr(service.subprocess, "run", fake)
    return fake


def _context(monkeypatch, context: str) -> None:
    monkeypatch.setattr("odoo_mcp_multi.cli._detect_install_context", lambda: context)


def _exec_start(unit_text: str) -> str:
    return next(line for line in unit_text.splitlines() if line.startswith("ExecStart="))


# -- what the unit runs, per install method --------------------------------


@pytest.mark.parametrize("context", ["pip", "pipx", "uv-tool", "uv-venv", "editable"])
def test_a_persistent_install_runs_its_own_interpreter(runner, linux, monkeypatch, context):
    """An absolute interpreter survives upgrades and never picks another odoo-mcp from PATH."""
    _context(monkeypatch, context)
    result = runner.invoke(main, ["service", "install", "--dry-run", "--port", "5099"])
    assert result.exit_code == 0, result.output
    assert _exec_start(result.output) == (
        f"ExecStart={sys.executable} -m odoo_mcp_multi serve --auth local --host 127.0.0.1 --port 5099"
    )
    assert f"for a {context} install" in result.output


def test_uvx_runs_through_uvx_pinned_to_this_version(runner, linux, monkeypatch):
    """uv may prune the cached environment; uvx rebuilds it, on the version that was installed."""
    _context(monkeypatch, "uvx")
    result = runner.invoke(main, ["service", "install", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert _exec_start(result.output) == (
        f"ExecStart=/usr/bin/uvx --from odoo-mcp-multi=={__version__} odoo-mcp "
        "serve --auth local --host 127.0.0.1 --port 5010"
    )


def test_uvx_from_overrides_the_package_spec(runner, linux, monkeypatch):
    _context(monkeypatch, "uvx")
    result = runner.invoke(main, ["service", "install", "--dry-run", "--uvx-from", "/tmp/odoo_mcp_multi.whl"])
    assert "--from /tmp/odoo_mcp_multi.whl odoo-mcp" in _exec_start(result.output)


def test_uvx_without_uvx_on_path_is_refused(runner, linux, monkeypatch):
    _context(monkeypatch, "uvx")
    monkeypatch.setattr(service.shutil, "which", lambda name: None)
    result = runner.invoke(main, ["service", "install", "--dry-run"])
    assert result.exit_code == 1
    assert "uvx is not on PATH" in result.output


def test_the_profile_is_passed_to_serve(runner, linux, monkeypatch):
    _context(monkeypatch, "pip")
    result = runner.invoke(main, ["service", "install", "--dry-run", "-p", "prod"])
    assert _exec_start(result.output).endswith("--port 5010 --profile prod")


def test_arguments_are_quoted_for_systemd():
    """systemd splits on spaces and expands %-specifiers."""
    unit = service.render_unit(["/opt/my env/python", "-m", "odoo_mcp_multi", "--profile", "100%"], "pip", "/opt/100%")
    assert _exec_start(unit) == 'ExecStart="/opt/my env/python" -m odoo_mcp_multi --profile 100%%'
    assert "WorkingDirectory=/opt/100%%\n" in unit


def _working_directory(unit_text: str) -> str:
    return next(line for line in unit_text.splitlines() if line.startswith("WorkingDirectory="))


@pytest.mark.parametrize("context", ["pip", "pipx", "uv-tool", "uv-venv", "editable"])
def test_a_persistent_install_starts_in_its_environment(runner, linux, monkeypatch, context):
    """`python -m` imports from the working directory first: never start next to a checkout."""
    _context(monkeypatch, context)
    result = runner.invoke(main, ["service", "install", "--dry-run"])
    assert _working_directory(result.output) == f"WorkingDirectory={sys.prefix}"


def test_uvx_starts_in_the_home_directory(runner, linux, monkeypatch, tmp_path):
    _context(monkeypatch, "uvx")
    monkeypatch.setattr(service.Path, "home", lambda: tmp_path)
    result = runner.invoke(main, ["service", "install", "--dry-run"])
    assert _working_directory(result.output) == f"WorkingDirectory={tmp_path}"


# -- installing -------------------------------------------------------------


def test_dry_run_changes_nothing(runner, linux, monkeypatch, tmp_path):
    _context(monkeypatch, "pip")
    result = runner.invoke(main, ["service", "install", "--dry-run"])
    assert result.exit_code == 0
    assert linux.calls == []
    assert not service.unit_path().exists()
    assert not (tmp_path / "odoo-mcp" / "local-token").exists()


def test_install_writes_enables_restarts_and_waits_for_the_port(runner, linux, monkeypatch, tmp_path):
    _context(monkeypatch, "pipx")
    result = runner.invoke(main, ["service", "install"])

    assert result.exit_code == 0, result.output
    assert service.unit_path() == tmp_path / "xdg" / "systemd" / "user" / "odoo-mcp.service"
    assert "ExecStart=" in service.unit_path().read_text()
    assert linux.verbs == ["daemon-reload", "enable odoo-mcp.service", "restart odoo-mcp.service"]
    token_file = tmp_path / "odoo-mcp" / "local-token"
    assert token_file.stat().st_mode & 0o777 == 0o600
    assert f'--header "Authorization: Bearer $(cat {token_file})"' in result.output
    assert token_file.read_text().strip() not in result.output, "the token itself is never printed"
    assert "running on http://127.0.0.1:5010/mcp" in result.output


def test_no_start_enables_without_starting(runner, linux, monkeypatch):
    _context(monkeypatch, "pip")
    result = runner.invoke(main, ["service", "install", "--no-start"])
    assert result.exit_code == 0, result.output
    assert linux.verbs == ["daemon-reload", "enable odoo-mcp.service"]
    assert "enabled (not started)" in result.output


def test_a_service_that_never_listens_is_reported_with_its_log(runner, linux, monkeypatch):
    _context(monkeypatch, "pip")
    monkeypatch.setattr(service, "_port_open", lambda host, port: False)
    monkeypatch.setattr(service, "journal_tail", lambda lines=20: "Traceback: boom")
    result = runner.invoke(main, ["service", "install"])
    assert result.exit_code == 1
    assert "did not start listening on 127.0.0.1:5010" in result.output
    assert "Traceback: boom" in result.output


def test_a_missing_user_bus_points_to_linger(runner, linux, monkeypatch):
    _context(monkeypatch, "pip")
    linux.returncode = 1
    linux.stderr = "Failed to connect to bus: No medium found"
    result = runner.invoke(main, ["service", "install"])
    assert result.exit_code == 1
    assert "No medium found" in result.output
    assert "loginctl enable-linger" in result.output


# -- refusals ---------------------------------------------------------------


def test_other_platforms_are_refused(runner, linux, monkeypatch):
    monkeypatch.setattr(service.sys, "platform", "darwin")
    result = runner.invoke(main, ["service", "install", "--dry-run"])
    assert result.exit_code == 1
    assert "only runs on Linux" in result.output


def test_a_host_without_systemctl_is_refused_before_anything_is_written(runner, linux, monkeypatch, tmp_path):
    _context(monkeypatch, "pip")
    monkeypatch.setattr(service.shutil, "which", lambda name: None)
    result = runner.invoke(main, ["service", "install"])
    assert result.exit_code == 1
    assert "systemctl was not found" in result.output
    assert not service.unit_path().exists()
    assert not (tmp_path / "odoo-mcp" / "local-token").exists()


def test_dry_run_needs_no_systemd(runner, linux, monkeypatch):
    """CI images have no systemd; the dry run still shows what each installer gets."""
    _context(monkeypatch, "pip")
    monkeypatch.setattr(service.shutil, "which", lambda name: None)
    result = runner.invoke(main, ["service", "install", "--dry-run"])
    assert result.exit_code == 0, result.output


def test_a_public_bind_is_refused(runner, linux, monkeypatch):
    _context(monkeypatch, "pip")
    result = runner.invoke(main, ["service", "install", "--dry-run", "--host", "0.0.0.0"])
    assert result.exit_code == 1
    assert "Refusing to bind 0.0.0.0" in result.output


def test_an_unknown_profile_is_refused(runner, linux, monkeypatch):
    _context(monkeypatch, "pip")
    monkeypatch.setattr("odoo_mcp_multi.cli.get_profile", lambda name: None)
    result = runner.invoke(main, ["service", "install", "--dry-run", "-p", "nope"])
    assert result.exit_code == 1
    assert "Profile 'nope' not found" in result.output


# -- uninstall and status ---------------------------------------------------


def test_uninstall_stops_disables_and_removes_the_unit(runner, linux, monkeypatch):
    _context(monkeypatch, "pip")
    runner.invoke(main, ["service", "install"])
    linux.calls.clear()

    result = runner.invoke(main, ["service", "uninstall"])

    assert result.exit_code == 0, result.output
    assert not service.unit_path().exists()
    assert linux.verbs == ["disable --now odoo-mcp.service", "daemon-reload"]


def test_uninstall_without_a_unit_says_so(runner, linux):
    result = runner.invoke(main, ["service", "uninstall"])
    assert result.exit_code == 0
    assert "is not installed" in result.output
    assert linux.calls == []


def test_status_without_a_unit_exits_3(runner, linux):
    result = runner.invoke(main, ["service", "status"])
    assert result.exit_code == 3
    assert "is not installed" in result.output


def test_status_passes_systemd_through(runner, linux, monkeypatch):
    _context(monkeypatch, "pip")
    runner.invoke(main, ["service", "install"])
    result = runner.invoke(main, ["service", "status"])
    assert result.exit_code == 0
    assert linux.verbs[-1] == "status --no-pager odoo-mcp.service"


def test_port_open_tells_a_listening_port_from_a_closed_one():
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert service._port_open("127.0.0.1", port) is True
    assert service._port_open("127.0.0.1", port) is False

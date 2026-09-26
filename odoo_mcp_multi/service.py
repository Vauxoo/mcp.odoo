"""Run ``odoo-mcp serve --auth local`` as a per-user systemd service.

Linux only for now. The unit is a *user* unit: it runs as the person who
installed it, reads their ``profiles.json`` and their local token, and needs
no root. What it executes depends on how odoo-mcp-multi was installed:

* pip, pipx, ``uv tool`` and any other persistent environment: the
  interpreter of that environment with ``-m odoo_mcp_multi``. It is an
  absolute path that survives ``odoo-mcp upgrade``, and it never picks up a
  different ``odoo-mcp`` that happens to come first on PATH.
* uvx: the environment lives in uv's cache and may be pruned at any time, so
  the unit runs ``uvx --from odoo-mcp-multi==<this version>`` instead, which
  rebuilds it when needed. Pinning keeps the service on the version that was
  installed, like every other install method.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

UNIT_NAME = "odoo-mcp.service"
START_TIMEOUT_SECONDS = 20

_SAFE_ARG = re.compile(r"[\w@%+=:,./-]+")


class ServiceError(Exception):
    """Raised when the service cannot be installed or managed here."""


def check_platform() -> None:
    """Refuse early on systems this command does not support yet."""
    if not sys.platform.startswith("linux"):
        raise ServiceError(
            "`odoo-mcp service` manages a systemd user unit and only runs on Linux for now. "
            "On macOS and Windows start `odoo-mcp serve --auth local` yourself."
        )


def require_systemctl() -> None:
    """Refuse before touching anything when systemd is not there to run the unit."""
    if shutil.which("systemctl") is None:
        raise ServiceError("systemctl was not found: `odoo-mcp service` needs systemd.")


def unit_path() -> Path:
    """Where systemd looks for this user's units."""
    config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config_home) / "systemd" / "user" / UNIT_NAME


def exec_start(context: str, serve_args: list[str], uvx_from: str) -> list[str]:
    """The command the unit runs, for the given install context."""
    if context == "uvx":
        uvx = shutil.which("uvx")
        if uvx is None:
            raise ServiceError("This odoo-mcp runs under uvx, but uvx is not on PATH to start the service with.")
        return [uvx, "--from", uvx_from, "odoo-mcp", *serve_args]
    return [sys.executable, "-m", "odoo_mcp_multi", *serve_args]


def working_directory(context: str) -> str:
    """The directory the service starts in.

    ``python -m`` puts the working directory first on ``sys.path``, so a unit
    started next to an ``odoo_mcp_multi/`` folder (a checkout) would run that
    code instead of the installed package. The environment's own prefix never
    holds one. uvx runs a console script, which does not import from the
    working directory, so the home directory is enough there.
    """
    return str(Path.home()) if context == "uvx" else sys.prefix


def _quote(arg: str) -> str:
    """Quote one ExecStart argument the way systemd parses it (``%`` is a specifier)."""
    arg = arg.replace("%", "%%")
    if _SAFE_ARG.fullmatch(arg):
        return arg
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_unit(command: list[str], context: str, workdir: str) -> str:
    """The unit file text."""
    return (
        "[Unit]\n"
        "Description=odoo-mcp shared MCP server for this user (serve --auth local)\n"
        "Documentation=https://git.vauxoo.com/ai/mcp.odoo/-/blob/main/docs/http-mode.md\n"
        "\n"
        "[Service]\n"
        f"# Written by `odoo-mcp service install` for a {context} install.\n"
        f"ExecStart={' '.join(_quote(arg) for arg in command)}\n"
        f"WorkingDirectory={workdir.replace('%', '%%')}\n"
        "Environment=PYTHONUNBUFFERED=1\n"
        "Restart=on-failure\n"
        "RestartSec=2\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def systemctl(*args: str) -> subprocess.CompletedProcess:
    """Run ``systemctl --user`` and capture its output."""
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def _checked(*args: str) -> None:
    result = systemctl(*args)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ServiceError(
            f"`systemctl --user {' '.join(args)}` failed: {detail}\n"
            "If there is no user session bus (SSH without a login session, containers), run "
            "`loginctl enable-linger $USER` and log in again."
        )


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def journal_tail(lines: int = 20) -> str:
    result = subprocess.run(
        ["journalctl", "--user", "-u", UNIT_NAME, "-n", str(lines), "--no-pager"], capture_output=True, text=True
    )
    return (result.stdout or result.stderr).strip()


def install(unit_text: str, host: str, port: int, start: bool = True) -> Path:
    """Write the unit, enable it and, unless told not to, (re)start it and wait for the port."""
    path = unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit_text, encoding="utf-8")
    _checked("daemon-reload")
    _checked("enable", UNIT_NAME)
    if not start:
        return path
    _checked("restart", UNIT_NAME)
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _port_open(host, port):
            return path
        if systemctl("is-failed", "--quiet", UNIT_NAME).returncode == 0:
            break
        time.sleep(0.25)
    raise ServiceError(f"{UNIT_NAME} did not start listening on {host}:{port}. Last log lines:\n{journal_tail()}")


def uninstall() -> Optional[Path]:
    """Stop, disable and remove the unit. Returns its path, or None if it was not installed."""
    path = unit_path()
    if not path.exists():
        return None
    systemctl("disable", "--now", UNIT_NAME)
    path.unlink()
    _checked("daemon-reload")
    return path

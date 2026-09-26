"""Check that `odoo-mcp service install` would start the right odoo-mcp.

CI images have no systemd, so the unit is rendered with --dry-run and its
ExecStart is executed for real, with `serve ...` replaced by `--version`: the
command the service would run must exist, start, and be the version under
test. The real systemd run lives in service_systemd.sh.

Usage: service_dry_run.py VERSION ODOO_MCP_COMMAND...
PACKAGE (the spec the job installed) is read from the environment; when it is
a wheel file, uvx is pointed at it instead of PyPI.
"""

import os
import shlex
import subprocess
import sys

version, command = sys.argv[1], sys.argv[2:]
package = os.environ.get("PACKAGE", "")
extra = ["--uvx-from", os.path.abspath(package)] if os.path.isfile(package) else []

unit = subprocess.run(
    [*command, "service", "install", "--dry-run", *extra], capture_output=True, text=True, check=True
).stdout
print(unit)
exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
argv = shlex.split(exec_start.removeprefix("ExecStart=").replace("%%", "%"))
argv = argv[: argv.index("serve")] + ["--version"]

result = subprocess.run(argv, capture_output=True, text=True)
print(f"$ {shlex.join(argv)}\n{result.stdout}{result.stderr}")
assert result.returncode == 0, "the command the service would run does not start"
assert version in result.stdout, f"the service would run another version than {version}"
print("OK: the unit starts the odoo-mcp this job installed")

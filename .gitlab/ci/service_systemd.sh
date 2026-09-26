#!/usr/bin/env bash
# End-to-end check of `odoo-mcp service` against a real systemd user manager,
# once per installer (pip, pipx, uv tool, uvx). Runs as root inside the
# container built from service_systemd.Dockerfile, with the checkout mounted
# at /src and a built wheel in /src/dist. See the Dockerfile for how to run it.
set -euo pipefail

WHEEL="$(ls /src/dist/*.whl)"
PORT=5011
USER_NAME=tester
USER_ID="$(id -u "$USER_NAME")"

loginctl enable-linger "$USER_NAME"
for _ in $(seq 1 50); do [ -S "/run/user/$USER_ID/bus" ] && break; sleep 0.2; done

as_user() {
    runuser -u "$USER_NAME" -- env HOME="/home/$USER_NAME" \
        XDG_RUNTIME_DIR="/run/user/$USER_ID" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$USER_ID/bus" \
        PATH="/home/$USER_NAME/.local/bin:/home/$USER_NAME/venv/bin:/usr/local/bin:/usr/bin:/bin" \
        UV_PYTHON_PREFERENCE=only-system bash -c "$1"
}

ping_status() {  # $1: "token" to send the local token, anything else to send none
    as_user "python3 - '$1' <<'EOF'
import json, sys, urllib.request, urllib.error, pathlib
headers = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}
if sys.argv[1] == 'token':
    token = (pathlib.Path.home() / '.config/odoo-mcp/local-token').read_text().strip()
    headers['Authorization'] = f'Bearer {token}'
body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}).encode()
request = urllib.request.Request('http://127.0.0.1:$PORT/mcp', data=body, headers=headers)
try:
    print(urllib.request.urlopen(request, timeout=5).status)
except urllib.error.HTTPError as exc:
    print(exc.code)
EOF"
}

expect() {  # $1: description, $2: expected, $3: actual
    if [ "$2" != "$3" ]; then
        echo "FAIL [$METHOD] $1: expected '$2', got '$3'"
        as_user "journalctl --user -u odoo-mcp.service -n 30 --no-pager" || true
        exit 1
    fi
    echo "ok   [$METHOD] $1"
}

wait_active() {
    for _ in $(seq 1 80); do
        [ "$(ping_status token)" = "200" ] && return 0
        sleep 0.25
    done
    return 1
}

check_method() {  # $1: method, $2: install command, $3: odoo-mcp command, $4: ExecStart must contain, $5: uninstall
    METHOD="$1"
    as_user "$2" >/dev/null
    local cli="$3"

    as_user "$cli service install --port $PORT ${UVX_FROM:-}"
    expect "unit runs the $METHOD environment" "yes" \
        "$(as_user "grep -q -- '$4' ~/.config/systemd/user/odoo-mcp.service && echo yes || echo no")"
    expect "systemd reports it active" "active" "$(as_user 'systemctl --user is-active odoo-mcp.service' || true)"
    expect "ping with the token" "200" "$(ping_status token)"
    expect "ping without the token" "401" "$(ping_status none)"
    expect "status exits 0" "0" "$(as_user "$cli service status >/dev/null; echo \$?")"

    local pid_before restarts_before
    pid_before="$(as_user 'systemctl --user show -P MainPID odoo-mcp.service')"
    restarts_before="$(as_user 'systemctl --user show -P NRestarts odoo-mcp.service')"
    as_user "systemctl --user kill --signal=KILL odoo-mcp.service"
    sleep 3
    wait_active || true
    expect "systemd counted one restart after a crash" "$((restarts_before + 1))" \
        "$(as_user 'systemctl --user show -P NRestarts odoo-mcp.service')"
    expect "a new process serves after the crash" "yes" \
        "$(as_user "[ \"\$(systemctl --user show -P MainPID odoo-mcp.service)\" != '$pid_before' ] && echo yes || echo no")"
    expect "it answers again after the crash" "200" "$(ping_status token)"

    as_user "$cli service install --port $PORT ${UVX_FROM:-}" >/dev/null
    expect "a second install restarts it in place" "200" "$(ping_status token)"

    as_user "$cli service uninstall"
    expect "unit file removed" "no" "$(as_user 'test -e ~/.config/systemd/user/odoo-mcp.service && echo yes || echo no')"
    expect "port closed" "000" "$(ping_status token 2>/dev/null | grep -E '^[0-9]+$' || echo 000)"
    expect "status says not installed" "3" "$(as_user "$cli service status >/dev/null; echo \$?")"

    as_user "$5" >/dev/null 2>&1
}

as_user "python3 -m pip install --user --quiet pipx uv"

check_method pip \
    "python3 -m venv ~/venv && ~/venv/bin/pip install --quiet '$WHEEL'" \
    "~/venv/bin/odoo-mcp" \
    "/home/$USER_NAME/venv/bin/python" \
    "rm -rf ~/venv"

check_method pipx \
    "pipx install --quiet '$WHEEL'" \
    "odoo-mcp" \
    "/home/$USER_NAME/.local/share/pipx/venvs/odoo-mcp-multi/bin/python" \
    "pipx uninstall odoo-mcp-multi"

check_method uv-tool \
    "uv tool install --quiet '$WHEEL'" \
    "odoo-mcp" \
    "/home/$USER_NAME/.local/share/uv/tools/odoo-mcp-multi/bin/python" \
    "uv tool uninstall odoo-mcp-multi"

UVX_FROM="--uvx-from $WHEEL" check_method uvx \
    "true" \
    "uvx --from '$WHEEL' odoo-mcp" \
    "/home/$USER_NAME/.local/bin/uvx --from $WHEEL odoo-mcp serve" \
    "true"

echo "PASS: odoo-mcp service works under pip, pipx, uv tool and uvx"

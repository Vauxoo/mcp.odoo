"""Smoke-test an installed odoo-mcp the way an MCP client launches it.

Usage: python mcp_smoke.py EXPECTED_VERSION COMMAND [ARGS...]

COMMAND is whatever a client config would put in "command"/"args" before "run":
`odoo-mcp`, `/abs/path/to/odoo-mcp`, or `uvx --from <spec> odoo-mcp`. The script checks
the version, then speaks MCP over stdio: initialize, tools/list, and one real tool call
that needs no Odoo instance. Standard library only, so it runs on any bare image.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading

TIMEOUT = 120
PROTOCOL_VERSION = "2025-06-18"


def check_version(command: list[str], expected: str) -> None:
    output = subprocess.run(
        [*command, "--version"], capture_output=True, text=True, check=True, timeout=TIMEOUT
    ).stdout.strip()
    assert output == f"odoo-mcp, version {expected}", f"unexpected --version output: {output!r}"
    print(f"--version: {output}")


def check_mcp(command: list[str]) -> None:
    server = subprocess.Popen(
        [*command, "run"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in server.stdout], daemon=True).start()

    def send(message: dict) -> None:
        server.stdin.write(json.dumps(message) + "\n")
        server.stdin.flush()

    def request(request_id: int, method: str, params: dict) -> dict:
        send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            message = json.loads(lines.get(timeout=TIMEOUT))
            if message.get("id") == request_id:
                assert "error" not in message, f"{method} failed: {message['error']}"
                return message["result"]

    try:
        init = request(
            1,
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "odoo-mcp-ci-smoke", "version": "0"},
            },
        )
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        print(f"initialize: {init['serverInfo']}")

        tools = sorted(tool["name"] for tool in request(2, "tools/list", {})["tools"])
        assert "list_available_profiles" in tools, f"tools/list is missing list_available_profiles: {tools}"
        print(f"tools/list: {len(tools)} tools")

        call = request(3, "tools/call", {"name": "list_available_profiles", "arguments": {}})
        assert not call.get("isError"), f"list_available_profiles failed: {call}"
        print("tools/call list_available_profiles: ok")
    finally:
        server.stdin.close()
        server.wait(timeout=TIMEOUT)


if __name__ == "__main__":
    expected_version, *command = sys.argv[1:]
    check_version(command, expected_version)
    check_mcp(command)

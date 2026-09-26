"""Tests for serving the MCP tools to several clients from one process.

Covers the two properties a shared server needs: a slow Odoo call must not
block the other clients, and ``serve --auth local`` must only answer on
loopback with Host/Origin validation while exposing this machine's profiles.
The end-to-end tests start ``odoo-mcp serve --auth local`` in a subprocess
with a throwaway HOME and talk to it over HTTP.
"""

import asyncio
import inspect
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from mcp import ClientSession

try:
    from mcp.client.streamable_http import streamable_http_client
except ImportError:  # mcp < 1.24 only has the older name; both take a bare URL
    from mcp.client.streamable_http import streamablehttp_client as streamable_http_client

from odoo_mcp_multi import server
from odoo_mcp_multi.server import mcp

SLOW_CALL_SECONDS = 0.5


def _slow_count(*_args, **_kwargs):
    time.sleep(SLOW_CALL_SECONDS)
    return {"success": True, "model": "res.partner", "count": 1}


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_search_count", side_effect=_slow_count)
async def test_slow_tool_calls_run_concurrently(_mock_op):
    """Two blocking tool calls overlap instead of queueing on the event loop."""
    start = time.perf_counter()
    await asyncio.gather(
        mcp.call_tool("search_count", {"model": "res.partner"}),
        mcp.call_tool("search_count", {"model": "res.partner"}),
    )
    elapsed = time.perf_counter() - start
    assert elapsed < SLOW_CALL_SECONDS * 1.6


@pytest.mark.asyncio
@patch("odoo_mcp_multi.server.op_search_count", side_effect=_slow_count)
async def test_event_loop_stays_responsive_during_a_tool_call(_mock_op):
    """The loop keeps serving other work while a tool waits on Odoo."""
    call = asyncio.ensure_future(mcp.call_tool("search_count", {"model": "res.partner"}))
    start = time.perf_counter()
    await asyncio.sleep(0.05)
    assert time.perf_counter() - start < SLOW_CALL_SECONDS / 2
    await call


@pytest.mark.asyncio
async def test_tool_schemas_come_from_the_sync_functions():
    """Each tool keeps the name, docstring and parameters of its function."""
    for tool in await mcp.list_tools():
        fn = getattr(server, tool.name)
        assert not inspect.iscoroutinefunction(fn)
        assert tool.description == fn.__doc__
        assert set(tool.inputSchema["properties"]) == set(inspect.signature(fn).parameters)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def http_server(tmp_path: Path):
    """Run ``odoo-mcp serve --auth local`` with one profile in a fresh HOME."""
    port = _free_port()
    env = {**os.environ, "HOME": str(tmp_path)}
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from odoo_mcp_multi.config import OdooProfile, add_profile; "
            "add_profile(OdooProfile(name='local-test', url='http://127.0.0.1:1', database='db', user='u', "
            "password='p'), set_default=True)",
        ],
        env=env,
        check=True,
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", "from odoo_mcp_multi.cli import main; main()", "serve", "--auth", "local"]
        + ["--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            if proc.poll() is not None:
                pytest.fail(f"server exited early: {proc.stderr.read().decode()}")
    else:
        proc.kill()
        pytest.fail("server did not start listening")
    yield port
    proc.terminate()
    proc.wait(timeout=10)


@pytest.mark.asyncio
async def test_local_mode_serves_the_tools_with_this_machines_profiles(http_server):
    """A client connects over HTTP, lists the tools and sees profiles.json."""
    async with streamable_http_client(f"http://127.0.0.1:{http_server}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("list_available_profiles", {})
    assert len(tools.tools) == 13
    assert [p["name"] for p in json.loads(result.content[0].text)] == ["local-test"]


def _ping(port: int, **headers) -> httpx.Response:
    return httpx.post(
        f"http://127.0.0.1:{port}/mcp",
        headers={"Accept": "application/json, text/event-stream", **headers},
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
    )


def test_local_mode_rejects_a_foreign_host_header(http_server):
    """Requests whose Host is not loopback are refused (DNS rebinding)."""
    assert _ping(http_server, Host="attacker.example").status_code == 421


@pytest.mark.parametrize("origin", ["https://attacker.example", "https://claude.ai"])
def test_local_mode_rejects_a_foreign_origin(http_server, origin):
    """A browser page on another origin cannot drive the unauthenticated server."""
    assert _ping(http_server, Origin=origin).status_code == 403

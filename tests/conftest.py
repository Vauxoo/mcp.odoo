"""Shared fixtures for the HTTP transport tests.

Every HTTP test drives the real ASGI application through an in-memory
transport: no sockets, no subprocesses, no live Odoo. The Odoo client is the
only thing mocked, and always at :func:`odoo_mcp_multi.client.create_client`,
so the operations layer under test is the real one.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

PUBLIC_HOST = "odoo-mcp.me1980.com"
PUBLIC_URL = f"https://{PUBLIC_HOST}/mcp"


@pytest.fixture
def http_config(tmp_path):
    """A serve configuration backed by throwaway state."""
    from odoo_mcp_multi.http.settings import HttpServeConfig

    return HttpServeConfig(
        host="127.0.0.1",
        port=5010,
        path="/mcp",
        public_url=PUBLIC_URL,
        state_db=tmp_path / "http-state.db",
        secret_key_file=tmp_path / "http-secret.key",
    )


@pytest.fixture
def auth_store(http_config):
    """The authorization store the app under test will use."""
    from odoo_mcp_multi.http.crypto import CredentialCipher
    from odoo_mcp_multi.http.store import AuthStore

    return AuthStore(http_config.state_db, CredentialCipher.from_file(http_config.secret_key_file))


@pytest.fixture
def http_app(http_config):
    """The full ASGI application, including the OAuth endpoints."""
    from odoo_mcp_multi.http.app import build_http_app

    return build_http_app(http_config)


class _Lifespan:
    """Run an ASGI lifespan for the duration of a test.

    httpx's ASGI transport never runs the lifespan, and the MCP session
    manager only creates its task group there. The lifespan is driven from a
    dedicated task because the task group inside it holds an anyio cancel
    scope, which must be entered and exited from the same task — fixture
    teardown does not guarantee that on its own.
    """

    def __init__(self, app) -> None:
        self.app = app
        self._started = asyncio.Event()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._error: BaseException | None = None

    async def _run(self) -> None:
        try:
            async with self.app.router.lifespan_context(self.app):
                self._started.set()
                await self._stop.wait()
        except BaseException as exc:  # noqa: BLE001 - surfaced to the test
            self._error = exc
            self._started.set()

    async def __aenter__(self) -> "_Lifespan":
        self._task = asyncio.create_task(self._run())
        await self._started.wait()
        if self._error is not None:
            raise self._error
        return self

    async def __aexit__(self, *_exc_info) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task


@pytest.fixture
async def client(http_app):
    """An httpx client wired straight into the ASGI app, lifespan running."""
    transport = httpx.ASGITransport(app=http_app)
    async with _Lifespan(http_app):
        async with httpx.AsyncClient(
            transport=transport, base_url=f"https://{PUBLIC_HOST}", follow_redirects=False
        ) as http_client:
            yield http_client


@pytest.fixture(autouse=True)
def _clear_request_profile():
    """Keep the per-request credential contextvar from leaking between tests."""
    from odoo_mcp_multi import context

    token = context.set_request_profile(None)
    yield
    context.reset_request_profile(token)

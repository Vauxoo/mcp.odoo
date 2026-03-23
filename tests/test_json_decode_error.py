import json

import httpx
import pytest

from odoo_mcp_multi.utils import JsonRpcClient, OdooConnectionError


class MockResponse:
    def __init__(self, status_code, content, headers=None):
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8") if isinstance(content, bytes) else content
        self.headers = headers or {}

    def json(self):
        return json.loads(self.content)


def test_json_decode_error(monkeypatch):
    client = JsonRpcClient("https://odoo.example.com", "test_db", "admin", "password")

    def mock_post(*args, **kwargs):
        return MockResponse(502, b"<html>Bad Gateway</html>")

    monkeypatch.setattr(httpx, "post", mock_post)

    with pytest.raises(OdooConnectionError, match="Invalid JSON response from server \\(HTTP 502\\): .*"):
        client._call("common", "authenticate", [])


def test_rate_limit_hint(monkeypatch):
    """When Odoo SaaS returns a 200 OK HTML page, include rate-limit hint."""
    client = JsonRpcClient("https://odoo.example.com", "test_db", "admin", "password")

    def mock_post(*args, **kwargs):
        return MockResponse(200, b"<h1>200 OK</h1>\nService ready")

    monkeypatch.setattr(httpx, "post", mock_post)

    with pytest.raises(OdooConnectionError, match=".*Odoo SaaS rate-limit.*Wait 30-60 seconds.*"):
        client._call("object", "execute_kw", [])


def test_cloudflare_hint(monkeypatch):
    """When Cloudflare blocks the request, include cloudflare hint."""
    client = JsonRpcClient("https://odoo.example.com", "test_db", "admin", "password")

    def mock_post(*args, **kwargs):
        return MockResponse(
            403,
            b"<html>Cloudflare challenge</html>",
            headers={"server": "cf-ray/123"},
        )

    monkeypatch.setattr(httpx, "post", mock_post)

    with pytest.raises(OdooConnectionError, match=".*Cloudflare challenge.*Wait 60 seconds.*"):
        client._call("object", "execute_kw", [])


def test_generic_html_hint(monkeypatch):
    """When a generic HTML page is returned, include proxy error hint."""
    client = JsonRpcClient("https://odoo.example.com", "test_db", "admin", "password")

    def mock_post(*args, **kwargs):
        return MockResponse(200, b"<!DOCTYPE html><html><body>Maintenance</body></html>")

    monkeypatch.setattr(httpx, "post", mock_post)

    with pytest.raises(OdooConnectionError, match=".*HTML page instead of JSON.*rate-limit.*"):
        client._call("object", "execute_kw", [])

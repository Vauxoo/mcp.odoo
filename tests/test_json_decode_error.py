import pytest
import httpx
from odoo_mcp_multi.utils import JsonRpcClient, OdooConnectionError
import json

class MockResponse:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content

    def json(self):
        return json.loads(self.content)

def test_json_decode_error(monkeypatch):
    client = JsonRpcClient("https://odoo.example.com", "test_db", "admin", "password")

    def mock_post(*args, **kwargs):
        return MockResponse(502, b"<html>Bad Gateway</html>")

    monkeypatch.setattr(httpx, "post", mock_post)

    with pytest.raises(OdooConnectionError, match="Invalid JSON response from server \\(HTTP 502\\): .*"):
        client._call("common", "authenticate", [])

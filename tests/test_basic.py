import json
from pathlib import Path

from odoo_mcp_multi import __version__, cli, config, server, utils


def test_imports():
    """Verify that all main modules can be imported successfully."""
    assert cli is not None
    assert server is not None
    assert config is not None
    assert utils is not None


def test_version():
    """Verify that the package has a version."""
    assert __version__ == "0.12.0"


def test_plugin_json_version():
    """Verify that plugin.json version matches package __version__."""
    plugin_json_path = (
        Path(__file__).parent.parent
        / "odoo_mcp_multi"
        / "plugins"
        / "odoo-mcp"
        / "plugin.json"
    )
    data = json.loads(plugin_json_path.read_text(encoding="utf-8"))
    assert data["version"] == __version__

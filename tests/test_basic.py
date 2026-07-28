import json
import re
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


PLUGIN_DIR = Path(__file__).parent.parent / "odoo_mcp_multi" / "plugins" / "odoo-mcp"


def test_antigravity_manifest_is_schema_compliant():
    """The Antigravity plugin.json allows only $schema, name and description."""
    data = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    assert set(data) <= {"$schema", "name", "description"}
    assert data["name"] == PLUGIN_DIR.name
    assert re.fullmatch(r"[a-zA-Z0-9-_]+", data["name"])


def test_claude_plugin_manifest_version():
    """The Claude Code plugin manifest tracks the package __version__."""
    data = json.loads((PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["version"] == __version__
    assert data["name"] == PLUGIN_DIR.name

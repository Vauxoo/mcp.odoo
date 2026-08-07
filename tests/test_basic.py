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
    assert __version__ == "0.15.0"


REPO_ROOT = Path(__file__).parent.parent
PLUGIN_DIR = REPO_ROOT / "odoo_mcp_multi" / "plugins" / "odoo-mcp"


def test_changelog_release_contract():
    """CHANGELOG must keep the headers the release automation depends on.

    bump-my-version rewrites the literal "## [Unreleased]" header at release
    time (see [tool.bumpversion.files] in pyproject.toml) and the
    release-notes CI job extracts the "## [<version>]" section as the GitLab
    Release description — losing either header silently breaks the next
    release or its announcement.
    """
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]" in changelog
    assert f"## [{__version__}]" in changelog


def test_antigravity_manifest_is_schema_compliant():
    """The Antigravity plugin.json allows only $schema, name and description."""
    data = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    assert set(data) <= {"$schema", "name", "description"}
    assert data["name"] == PLUGIN_DIR.name
    assert re.fullmatch(r"[a-zA-Z0-9-_]+", data["name"])


def test_claude_plugin_manifest():
    """The root Claude Code manifest tracks __version__ and wires skills + MCP.

    The manifest lives at the repo root because the ai/marketplace catalog
    only discovers .claude-plugin/plugin.json there, and the generated
    entry installs the whole repo as the plugin root.
    """
    data = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["version"] == __version__
    assert data["name"] == PLUGIN_DIR.name

    # The skills override must point at the packaged skills so the pip
    # layout and the plugin layout stay a single source of truth.
    skills_dir = REPO_ROOT / data["skills"]
    assert skills_dir.resolve() == (PLUGIN_DIR / "skills").resolve()
    bundled = [p.name for p in skills_dir.iterdir() if (p / "SKILL.md").exists()]
    assert len(bundled) >= 3

    # Installing the plugin also registers the MCP server via the
    # pip-installed CLI on PATH.
    assert data["mcpServers"]["odoo"] == {"command": "odoo-mcp", "args": ["run"]}

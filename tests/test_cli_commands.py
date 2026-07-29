"""CLI integration tests using Click's CliRunner.

Tests each new CLI command to verify argument handling, output format,
and error behavior — ensuring CLI and MCP are functionally equivalent.
"""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from odoo_mcp_multi.cli import _get_skills_dir, _install_plugin_or_skills, _validate_skill, main

runner = CliRunner()


# ---------------------------------------------------------------------------
# search-read
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_search_read")
def test_cli_search_read(mock_op):
    mock_op.return_value = {
        "records": [{"id": 1, "name": "Test"}],
        "total": 1,
        "limit": 100,
        "offset": 0,
        "has_more": False,
        "next_offset": 100,
    }

    result = runner.invoke(main, ["search-read", "--model", "res.partner", "--fields", "id,name"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert len(output["records"]) == 1
    assert output["records"][0]["name"] == "Test"
    assert output["has_more"] is False


@patch("odoo_mcp_multi.cli.op_search_read")
def test_cli_search_read_with_options(mock_op):
    mock_op.return_value = {"records": [], "total": 0, "has_more": False, "format": "json"}

    result = runner.invoke(
        main,
        [
            "search-read",
            "--model",
            "res.partner",
            "--domain",
            "[('active','=',True)]",
            "--fields",
            "name",
            "--limit",
            "10",
            "--offset",
            "5",
            "--order",
            "name asc",
            "--profile",
            "prod",
        ],
    )

    assert result.exit_code == 0
    mock_op.assert_called_once_with("res.partner", "[('active','=',True)]", "name", 10, 5, "name asc", "json", "prod")


@patch("odoo_mcp_multi.cli.op_search_read")
def test_cli_search_read_format_flag(mock_op):
    """--format flag is passed through to op_search_read."""
    mock_op.return_value = {"data": "| id |\n| --- |\n| 1 |", "total": 1, "format": "table"}

    result = runner.invoke(
        main,
        ["search-read", "--model", "res.partner", "--format", "compact", "--profile", "dev"],
    )

    assert result.exit_code == 0
    mock_op.assert_called_once_with("res.partner", "[]", "", 25, 0, "", "compact", "dev")


@patch("odoo_mcp_multi.cli.op_search_read", return_value={"success": False, "error": "No Odoo profile configured."})
def test_cli_search_read_error(mock_op):
    result = runner.invoke(main, ["search-read", "--model", "res.partner"])
    assert result.exit_code == 1
    assert "ERROR:" in result.output
    assert "No Odoo profile" in result.output


# ---------------------------------------------------------------------------
# search-count
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_search_count")
def test_cli_search_count(mock_op):
    mock_op.return_value = {"success": True, "model": "res.partner", "count": 42}

    result = runner.invoke(main, ["search-count", "--model", "res.partner", "--domain", "[('a','=',1)]"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["count"] == 42
    mock_op.assert_called_once_with("res.partner", "[('a','=',1)]", None)


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_write")
def test_cli_write(mock_op):
    mock_op.return_value = {"success": True, "updated_ids": [1]}

    result = runner.invoke(main, ["write", "--model", "res.partner", "--ids", "1", "--values", '{"name": "Updated"}'])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["success"] is True


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_create")
def test_cli_create(mock_op):
    mock_op.return_value = {"success": True, "id": 42}

    result = runner.invoke(main, ["create", "--model", "res.partner", "--values", '{"name": "New"}'])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["id"] == 42


# ---------------------------------------------------------------------------
# export-records
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_export_records")
def test_cli_export_records(mock_op):
    mock_op.return_value = {
        "records": [{"id": "ext_1", "name": "A"}],
        "total": 1,
        "limit": 500,
        "offset": 0,
        "has_more": False,
        "next_offset": 500,
    }

    result = runner.invoke(main, ["export-records", "--model", "res.partner", "--fields", "id,name"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert len(output["records"]) == 1


# ---------------------------------------------------------------------------
# import-records
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_import_records")
def test_cli_import_records(mock_op):
    mock_op.return_value = {"ids": [1], "messages": []}

    rows = json.dumps([{"id": "ext_1", "name": "Test"}])
    result = runner.invoke(main, ["import-records", "--model", "res.partner", "--fields", "id,name", "--rows", rows])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["ids"] == [1]


# ---------------------------------------------------------------------------
# execute-kw
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_execute_kw")
def test_cli_execute_kw(mock_op):
    mock_op.return_value = {"success": True, "result": True}

    result = runner.invoke(
        main, ["execute-kw", "--model", "sale.order", "--method", "action_confirm", "--args", "[[42]]"]
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["success"] is True


# ---------------------------------------------------------------------------
# get-version
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_get_version")
def test_cli_get_version(mock_op):
    mock_op.return_value = {"server_version": "17.0"}

    result = runner.invoke(main, ["get-version"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["server_version"] == "17.0"


@patch("odoo_mcp_multi.cli.op_get_version", return_value={"success": False, "error": "No Odoo profile configured."})
def test_cli_get_version_error(mock_op):
    result = runner.invoke(main, ["get-version"])
    assert result.exit_code == 1
    assert "ERROR:" in result.output
    assert "No Odoo profile" in result.output


# ---------------------------------------------------------------------------
# list-models
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_list_models")
def test_cli_list_models(mock_op):
    mock_op.return_value = {"success": True, "models": [{"name": "Contact", "model": "res.partner", "info": ""}]}

    result = runner.invoke(main, ["list-models", "--search", "partner"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["models"][0]["model"] == "res.partner"


# ---------------------------------------------------------------------------
# list-fields
# ---------------------------------------------------------------------------


@patch("odoo_mcp_multi.cli.op_list_fields")
def test_cli_list_fields(mock_op):
    mock_op.return_value = {"name": {"string": "Name", "type": "char"}}

    result = runner.invoke(main, ["list-fields", "--model", "res.partner"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert "name" in output
    assert output["name"]["type"] == "char"


# ---------------------------------------------------------------------------
# Verify --help works for all new commands
# ---------------------------------------------------------------------------


def test_cli_help():
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    # All new commands should be listed
    for cmd in [
        "search-read",
        "write",
        "create",
        "export-records",
        "import-records",
        "execute-kw",
        "get-version",
        "list-models",
        "list-fields",
    ]:
        assert cmd in result.output, f"Command '{cmd}' not found in --help output"


def test_cli_search_read_help():
    result = runner.invoke(main, ["search-read", "--help"])
    assert result.exit_code == 0
    assert "--model" in result.output
    assert "--domain" in result.output
    assert "--format" in result.output
    assert "compact" in result.output
    assert "table" in result.output
    assert "html" in result.output
    assert "csv" in result.output


# ---------------------------------------------------------------------------
# plugins & skills
# ---------------------------------------------------------------------------


def test_cli_plugins_help():
    result = runner.invoke(main, ["plugins", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "install" in result.output


def test_cli_plugins_list():
    result = runner.invoke(main, ["plugins", "list"])
    assert result.exit_code == 0
    assert "Available skills in odoo-mcp plugin:" in result.output
    assert "odoo-mcp-cli" in result.output


def test_cli_skills_help():
    result = runner.invoke(main, ["skills", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "install" in result.output


def test_cli_skills_list():
    result = runner.invoke(main, ["skills", "list"])
    assert result.exit_code == 0
    assert "Available skills in odoo-mcp plugin:" in result.output
    assert "odoo-mcp-cli" in result.output


def test_cli_plugins_install_antigravity_layout(tmp_path, monkeypatch):
    """Antigravity install places plugin.json plus every skill in the plugin tree."""
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(main, ["plugins", "install", "antigravity"])
    assert result.exit_code == 0
    assert "Successfully installed for antigravity!" in result.output

    plugin_root = tmp_path / ".gemini" / "config" / "plugins" / "odoo-mcp"
    assert (plugin_root / "plugin.json").is_file()
    # Copies by default: real files, not symlinks into the package
    assert not (plugin_root / "plugin.json").is_symlink()
    skills = plugin_root / "skills"
    skill_names = sorted(p.name for p in skills.iterdir())
    assert "odoo-mcp-cli" in skill_names
    assert "odoo-financial-reports" in skill_names
    for skill in skills.iterdir():
        assert (skill / "SKILL.md").exists()


def test_cli_plugins_install_idempotent_and_force(tmp_path, monkeypatch):
    """Re-running without --force skips existing items; --force reinstalls them."""
    monkeypatch.setenv("HOME", str(tmp_path))
    assert runner.invoke(main, ["plugins", "install", "antigravity"]).exit_code == 0

    rerun = runner.invoke(main, ["plugins", "install", "antigravity"])
    assert rerun.exit_code == 0
    assert "Skipping" in rerun.output
    assert "0 installed" in rerun.output

    forced = runner.invoke(main, ["plugins", "install", "antigravity", "--force"])
    assert forced.exit_code == 0
    assert "Skipping" not in forced.output


def test_cli_skills_install_flat_agent(tmp_path, monkeypatch):
    """Flat agents get bare skill directories without the plugin manifest."""
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(main, ["skills", "install", "claude"])
    assert result.exit_code == 0
    target = tmp_path / ".claude" / "skills"
    assert (target / "odoo-mcp-tools" / "SKILL.md").exists()
    assert not (target / "plugin.json").exists()


def test_cli_plugins_install_symlink_mode(tmp_path, monkeypatch):
    """--symlink links into the package source instead of copying."""
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(main, ["plugins", "install", "claude", "--symlink"])
    assert result.exit_code == 0
    target = tmp_path / ".claude" / "skills"
    assert (target / "odoo-mcp-tools").is_symlink()
    assert (target / "odoo-mcp-tools" / "SKILL.md").exists()


def test_cli_plugins_install_reports_failures(tmp_path, monkeypatch):
    """Install failures are reported per item and the command exits non-zero."""
    monkeypatch.setenv("HOME", str(tmp_path))
    with patch("odoo_mcp_multi.cli.shutil.copytree", side_effect=OSError("permission denied")):
        result = runner.invoke(main, ["plugins", "install", "claude"])
    assert result.exit_code == 1
    assert "Completed with errors" in result.output


def test_cli_plugins_install_without_skills_dir(tmp_path, monkeypatch):
    """A missing packaged skills directory aborts the install with an error."""
    monkeypatch.setenv("HOME", str(tmp_path))
    with patch("odoo_mcp_multi.cli._get_skills_dir", return_value=tmp_path / "missing"):
        result = runner.invoke(main, ["plugins", "install", "claude"])
    assert result.exit_code == 1
    assert "No skills found" in result.output


def test_install_unknown_agent_exits():
    """The shared install helper rejects agents outside AGENT_DIRS."""
    with pytest.raises(SystemExit):
        _install_plugin_or_skills("not-an-agent", force=False)


def test_cli_plugins_uninstall_antigravity(tmp_path, monkeypatch):
    """Uninstall removes the whole antigravity plugin directory."""
    monkeypatch.setenv("HOME", str(tmp_path))
    assert runner.invoke(main, ["plugins", "install", "antigravity"]).exit_code == 0
    plugin_root = tmp_path / ".gemini" / "config" / "plugins" / "odoo-mcp"
    assert plugin_root.exists()

    result = runner.invoke(main, ["plugins", "uninstall", "antigravity"])
    assert result.exit_code == 0
    assert not plugin_root.exists()


def test_cli_plugins_uninstall_flat_agent_only_own_skills(tmp_path, monkeypatch):
    """Flat uninstall removes only odoo-mcp skills, keeping unrelated ones."""
    monkeypatch.setenv("HOME", str(tmp_path))
    assert runner.invoke(main, ["plugins", "install", "claude"]).exit_code == 0
    target = tmp_path / ".claude" / "skills"
    foreign = target / "someone-elses-skill"
    foreign.mkdir()
    (foreign / "SKILL.md").write_text("---\nname: other\n---\n")

    result = runner.invoke(main, ["plugins", "uninstall", "claude"])
    assert result.exit_code == 0
    assert not (target / "odoo-mcp-tools").exists()
    assert foreign.exists()


def test_cli_plugins_uninstall_nothing_installed(tmp_path, monkeypatch):
    """Uninstall on a clean HOME reports nothing to do and exits 0."""
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(main, ["plugins", "uninstall", "claude"])
    assert result.exit_code == 0
    assert "Nothing to uninstall" in result.output


def test_bundled_skills_meet_cross_agent_contract():
    """Every packaged skill satisfies the strictest published frontmatter rules."""
    skills_dir = _get_skills_dir()
    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir() or not (item / "SKILL.md").exists():
            continue
        assert _validate_skill(item) == [], f"{item.name} violates the skill contract"


def test_cli_plugins_install_warns_on_contract_violations(tmp_path, monkeypatch):
    """Non-compliant frontmatter produces warnings but does not block install."""
    monkeypatch.setenv("HOME", str(tmp_path))
    bad_skills = tmp_path / "bundled-skills"
    bad_skill = bad_skills / "Bad_Skill"
    bad_skill.mkdir(parents=True)
    (bad_skill / "SKILL.md").write_text('---\nname: "other-name"\n---\nBody\n')

    with patch("odoo_mcp_multi.cli._get_skills_dir", return_value=bad_skills):
        result = runner.invoke(main, ["plugins", "install", "claude"])

    assert result.exit_code == 0
    assert "differs from directory name" in result.output
    assert "missing 'description'" in result.output
    assert "Successfully installed" in result.output

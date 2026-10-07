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


def test_cli_plugins_install_agy_is_plugin_alias(tmp_path, monkeypatch):
    """The agy target installs the same plugin tree as antigravity."""
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = tmp_path / ".gemini" / "config" / "skills"
    legacy.mkdir(parents=True)

    result = runner.invoke(main, ["skills", "install", "agy"])
    assert result.exit_code == 0
    assert "Successfully installed for agy!" in result.output

    plugin_root = tmp_path / ".gemini" / "config" / "plugins" / "odoo-mcp"
    assert (plugin_root / "plugin.json").is_file()
    assert (plugin_root / "skills" / "odoo-mcp-tools" / "SKILL.md").exists()
    # Nothing lands in the legacy flat skills directory anymore, and a
    # clean legacy directory triggers no purge message.
    assert not (legacy / "odoo-mcp-tools").exists()
    assert "Removing legacy flat skills" not in result.output


def test_cli_plugins_install_purges_legacy_agy_flat_skills(tmp_path, monkeypatch):
    """Plugin install removes flat copies left by pre-plugin agy installs."""
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = tmp_path / ".gemini" / "config" / "skills"
    stale = legacy / "odoo-mcp-tools"
    stale.mkdir(parents=True)
    (stale / "SKILL.md").write_text("---\nname: odoo-mcp-tools\n---\n")
    foreign = legacy / "someone-elses-skill"
    foreign.mkdir()
    (foreign / "SKILL.md").write_text("---\nname: other\n---\n")

    result = runner.invoke(main, ["plugins", "install", "antigravity"])
    assert result.exit_code == 0
    assert "Removing legacy flat skills" in result.output
    assert not stale.exists()
    assert foreign.exists()


def test_cli_plugins_uninstall_agy_removes_plugin_and_legacy(tmp_path, monkeypatch):
    """Uninstalling agy drops the plugin tree and legacy flat copies."""
    monkeypatch.setenv("HOME", str(tmp_path))
    assert runner.invoke(main, ["plugins", "install", "agy"]).exit_code == 0
    legacy_skill = tmp_path / ".gemini" / "config" / "skills" / "odoo-mcp-cli"
    legacy_skill.mkdir(parents=True)
    (legacy_skill / "SKILL.md").write_text("---\nname: odoo-mcp-cli\n---\n")

    result = runner.invoke(main, ["plugins", "uninstall", "agy"])
    assert result.exit_code == 0
    assert not (tmp_path / ".gemini" / "config" / "plugins" / "odoo-mcp").exists()
    assert not legacy_skill.exists()


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
    result = runner.invoke(main, ["skills", "install", "codex"])
    assert result.exit_code == 0
    target = tmp_path / ".agents" / "skills"
    assert (target / "odoo-mcp-tools" / "SKILL.md").exists()
    assert not (target / "plugin.json").exists()


def test_cli_skills_install_claude_migrates_flat_install(tmp_path, monkeypatch):
    """The claude target removes flat copies on confirmation and prints the plugin commands."""
    monkeypatch.setenv("HOME", str(tmp_path))
    flat = tmp_path / ".claude" / "skills" / "odoo-mcp-tools"
    flat.mkdir(parents=True)
    (flat / "SKILL.md").write_text("---\nname: odoo-mcp-tools\n---\n")

    result = runner.invoke(main, ["skills", "install", "claude"], input="y\n")
    assert result.exit_code == 0
    assert not flat.exists()
    assert "/plugin marketplace add https://git.vauxoo.com/ai/marketplace.git" in result.output
    assert "/plugin install odoo-mcp@vauxoo-ai" in result.output


def test_cli_skills_install_claude_keeps_flat_install_when_declined(tmp_path, monkeypatch):
    """Declining the cleanup keeps the flat copies and warns about duplicates."""
    monkeypatch.setenv("HOME", str(tmp_path))
    flat = tmp_path / ".claude" / "skills" / "odoo-mcp-tools"
    flat.mkdir(parents=True)
    (flat / "SKILL.md").write_text("---\nname: odoo-mcp-tools\n---\n")

    result = runner.invoke(main, ["skills", "install", "claude"], input="n\n")
    assert result.exit_code == 0
    assert flat.exists()
    assert "duplicate" in result.output
    assert "/plugin install odoo-mcp@vauxoo-ai" in result.output


def test_cli_skills_install_claude_clean_home_prints_commands_only(tmp_path, monkeypatch):
    """Without a previous flat install the claude target only prints the commands."""
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(main, ["skills", "install", "claude"])
    assert result.exit_code == 0
    assert not (tmp_path / ".claude" / "skills").exists()
    assert "Remove the deprecated flat skills" not in result.output
    assert "/plugin install odoo-mcp@vauxoo-ai" in result.output


def test_cli_plugins_install_symlink_mode(tmp_path, monkeypatch):
    """--symlink links into the package source instead of copying."""
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(main, ["plugins", "install", "codex", "--symlink"])
    assert result.exit_code == 0
    target = tmp_path / ".agents" / "skills"
    assert (target / "odoo-mcp-tools").is_symlink()
    assert (target / "odoo-mcp-tools" / "SKILL.md").exists()


def test_cli_plugins_install_reports_failures(tmp_path, monkeypatch):
    """Install failures are reported per item and the command exits non-zero."""
    monkeypatch.setenv("HOME", str(tmp_path))
    with patch("odoo_mcp_multi.cli.shutil.copytree", side_effect=OSError("permission denied")):
        result = runner.invoke(main, ["plugins", "install", "codex"])
    assert result.exit_code == 1
    assert "Completed with errors" in result.output


def test_cli_plugins_install_without_skills_dir(tmp_path, monkeypatch):
    """A missing packaged skills directory aborts the install with an error."""
    monkeypatch.setenv("HOME", str(tmp_path))
    with patch("odoo_mcp_multi.cli._get_skills_dir", return_value=tmp_path / "missing"):
        result = runner.invoke(main, ["plugins", "install", "codex"])
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
    assert runner.invoke(main, ["plugins", "install", "codex"]).exit_code == 0
    target = tmp_path / ".agents" / "skills"
    foreign = target / "someone-elses-skill"
    foreign.mkdir()
    (foreign / "SKILL.md").write_text("---\nname: other\n---\n")

    result = runner.invoke(main, ["plugins", "uninstall", "codex"])
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
        result = runner.invoke(main, ["plugins", "install", "codex"])

    assert result.exit_code == 0
    assert "differs from directory name" in result.output
    assert "missing 'description'" in result.output
    assert "Successfully installed" in result.output


# ---------------------------------------------------------------------------
# Profile permissions are enforced by the CLI too
# ---------------------------------------------------------------------------


def _write_granular_profile(home, allowed, execute_kw_allow=None):
    permissions = {"mode": "granular", "allowed_operations": allowed}
    if execute_kw_allow is not None:
        permissions["execute_kw_allow"] = execute_kw_allow
    config_dir = home / ".config" / "odoo-mcp"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.json").write_text(
        json.dumps(
            {
                "default_profile": "ro",
                "profiles": {
                    "ro": {
                        "name": "ro",
                        "url": "http://127.0.0.1:9",
                        "database": "demo",
                        "user": "admin",
                        "password": "admin",
                        "permissions": permissions,
                    }
                },
            }
        )
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["search-count", "-m", "res.partner"],
        ["write", "-m", "res.partner", "-i", "1", "-v", '{"name": "X"}'],
        ["unlink", "-m", "res.partner", "-i", "1"],
        ["create", "-m", "res.partner", "-v", '{"name": "X"}'],
        ["export-records", "-m", "res.partner"],
        ["import-records", "-m", "res.partner", "-f", "name", "-r", '[{"name": "X"}]'],
        ["execute-kw", "-m", "res.partner", "--method", "search_count", "-a", "[[]]"],
        ["list-models"],
        ["list-fields", "-m", "res.partner"],
        ["get-financial-report", "-r", "1"],
    ],
)
def test_cli_denies_operations_outside_the_profile(argv, tmp_path, monkeypatch):
    """A read-only profile blocks every other data command before any RPC."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_granular_profile(tmp_path, ["search_read"])

    with patch("odoo_mcp_multi.operations.create_client") as create_client:
        result = runner.invoke(main, [*argv, "-p", "ro"])

    assert result.exit_code == 1
    assert "is not allowed for profile 'ro'" in result.output
    create_client.assert_not_called()


def test_cli_allows_operations_in_the_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_granular_profile(tmp_path, ["search_count"])

    with patch("odoo_mcp_multi.operations.create_client") as create_client:
        create_client.return_value.execute_kw.return_value = 7
        create_client.return_value.last_warning = None
        result = runner.invoke(main, ["search-count", "-m", "res.partner", "-p", "ro"])

    assert result.exit_code == 0
    assert json.loads(result.output)["count"] == 7


@pytest.mark.parametrize(
    ("execute_kw_allow", "method", "allowed"),
    [
        (None, "unlink", False),
        (None, "action_confirm", True),
        ([{"model": "res.partner", "method": "message_post"}], "message_post", True),
        ([{"model": "res.partner", "method": "message_post"}], "action_confirm", False),
        ([{"model": "res.partner", "method": "unlink"}], "unlink", True),
    ],
)
def test_cli_execute_kw_honours_method_rules(execute_kw_allow, method, allowed, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_granular_profile(tmp_path, ["search_read", "execute_kw"], execute_kw_allow)

    with patch("odoo_mcp_multi.operations.create_client") as create_client:
        create_client.return_value.execute_kw.return_value = True
        create_client.return_value.last_warning = None
        result = runner.invoke(
            main, ["execute-kw", "-m", "res.partner", "--method", method, "-a", "[[1]]", "-p", "ro"]
        )

    if allowed:
        assert result.exit_code == 0
        create_client.return_value.execute_kw.assert_called_once()
    else:
        assert result.exit_code == 1
        assert f"Method 'res.partner.{method}' is not allowed through execute_kw" in result.output
        create_client.assert_not_called()

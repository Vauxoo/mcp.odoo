"""Click CLI for odoo-mcp-multi.

Provides commands for managing Odoo profiles and running the MCP server,
plus all Odoo data operations (search, write, create, etc.) mirroring
the MCP tool interface. Both interfaces share logic via operations.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

# Windows cp1252 consoles choke on Unicode glyphs — fall back to ASCII.
try:
    "\u2713\u2717".encode(sys.stdout.encoding or "utf-8")
    TICK, CROSS = "\u2713", "\u2717"
except (UnicodeEncodeError, LookupError):
    TICK, CROSS = "[OK]", "[FAIL]"

from odoo_mcp_multi import __version__
from odoo_mcp_multi.config import (
    OdooProfile,
    add_profile,
    get_profile,
    list_profiles,
    remove_profile,
    set_default_profile,
)
from odoo_mcp_multi.exceptions import OdooConnectionError
from odoo_mcp_multi.operations import (
    op_create,
    op_execute_kw,
    op_export_records,
    op_get_version,
    op_import_records,
    op_list_fields,
    op_list_models,
    op_search_read,
    op_test_connection,
    op_unlink,
    op_write,
)


def _output(data, as_json: bool = True) -> None:
    """Output data as formatted JSON to stdout."""
    click.echo(json.dumps(data, indent=2, default=str, ensure_ascii=False))


@click.group()
@click.version_option(version=__version__, prog_name="odoo-mcp")
def main() -> None:
    """MCP Server for connecting Claude/Cursor to multiple Odoo instances.

    Use 'odoo-mcp add-profile' to configure an Odoo instance,
    then 'odoo-mcp run' to start the MCP server.

    All Odoo data commands (search-read, write, create, etc.) are also
    available directly from the CLI.
    """
    pass


# ---------------------------------------------------------------------------
# Profile management commands
# ---------------------------------------------------------------------------


@main.command("add-profile")
@click.option("--name", prompt="Profile name", help="Unique identifier (e.g., 'prod', 'staging')")
@click.option("--url", prompt="Odoo URL", help="Instance URL (e.g., 'https://odoo.example.com')")
@click.option("--database", prompt="Database name", help="Odoo database name")
@click.option("--user", default=None, help="Odoo username (legacy auth, Odoo < 19)")
@click.option("--password", default=None, hide_input=True, help="Odoo password (legacy auth, Odoo < 19)")
@click.option("--api-key", "api_key", default=None, help="API key for Odoo 19+ Bearer auth (/json/2)")
@click.option("--protocol", default="auto", help="RPC protocol: auto, json2s, jsonrpcs, xmlrpcs (default: auto)")
@click.option("--default", "set_default", is_flag=True, help="Set as default profile")
@click.option("--test/--no-test", "test_connection", default=True, help="Test connection before saving")
def cmd_add_profile(
    name: str,
    url: str,
    database: str,
    user: str | None,
    password: str | None,
    api_key: str | None,
    protocol: str,
    set_default: bool,
    test_connection: bool,
) -> None:
    """Add a new Odoo profile with credentials.

    For Odoo < 19  (XML-RPC / JSON-RPC): use --user + --password.
    For Odoo >= 19 (JSON-2 REST API):     use --api-key.

    When the server is Odoo 19+ and --password is provided instead of
    --api-key, the credential is automatically stored as api_key
    (the JSON-2 protocol requires a Bearer token, not user/password).

    Examples:

      odoo-mcp add-profile --name prod --url https://odoo.example.com \\
          --database mydb --user admin --password

      odoo-mcp add-profile --name prod19 --url https://odoo19.example.com \\
          --database mydb --api-key YOUR_KEY --protocol json2s
    """
    # Validation: require at least one auth method
    if not password and not api_key:
        click.secho(
            f"{CROSS} Provide either --password (legacy) or --api-key (Odoo 19+).",
            fg="red",
        )
        raise SystemExit(1)

    # Detect server version to auto-migrate password → api_key for Odoo 19+
    from odoo_mcp_multi.parsers import normalize_url, parse_version
    from odoo_mcp_multi.version import get_server_version

    server_major = 0
    try:
        version_info = get_server_version(normalize_url(url))
        if version_info:
            ver_str = version_info.get("server_version", version_info.get("version", ""))
            server_major, _, _ = parse_version(ver_str)
    except Exception:
        pass

    if server_major >= 19 and password and not api_key:
        # Odoo 19+ requires Bearer token — treat the provided password as api_key
        api_key = password
        password = None
        click.secho(
            f"[WARN] Odoo {server_major} detected — credential stored as api_key (Bearer token).",
            fg="yellow",
        )

    if test_connection:
        click.echo(f"Testing connection to {url}...")
        try:
            if api_key:
                if version_info is None:
                    version_info = get_server_version(normalize_url(url))
                if version_info is None:
                    raise OdooConnectionError("Could not reach server (no version info)")
                ver = version_info.get("server_version", version_info.get("version", "unknown"))
                click.secho(f"{TICK} Server reachable! Odoo {ver}", fg="green")
            else:
                result = op_test_connection(url=url, database=database, user=user or "", password=password or "")
                if result.get("success") is False:
                    click.secho(f"{CROSS} Connection test failed: {result['error']}", fg="red")
                    if not click.confirm("Save profile anyway?"):
                        return
                else:
                    click.secho(
                        f"{TICK} Connection successful! Authenticated as UID {result['uid']}",
                        fg="green",
                    )
        except OdooConnectionError as e:
            click.secho(f"{CROSS} Connection failed: {e}", fg="red")
            if not click.confirm("Save profile anyway?"):
                return

    profile = OdooProfile(
        name=name,
        url=url,
        database=database,
        user=user or "",
        password=password if password else None,
        api_key=api_key if api_key else None,
        protocol=protocol,
    )
    add_profile(profile, set_default=set_default)
    auth_method = f"api_key ({protocol})" if api_key else "password"
    click.secho(f"{TICK} Profile '{name}' saved successfully! [auth: {auth_method}]", fg="green")

    if set_default:
        click.echo("  Set as default profile.")


@main.command("list-profiles")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def cmd_list_profiles(as_json: bool) -> None:
    """List all configured Odoo profiles."""
    profiles = list_profiles()

    if not profiles:
        click.echo("No profiles configured. Use 'odoo-mcp add-profile' to add one.")
        return

    if as_json:
        _output(profiles)
        return

    click.echo("\nConfigured Profiles:")
    click.echo("-" * 60)

    for p in profiles:
        default_marker = " (default)" if p["is_default"] else ""
        auth_display = p.get("auth", "unknown")
        click.echo(f"  {p['name']}{default_marker}")
        click.echo(f"    URL:      {p['url']}")
        click.echo(f"    Database: {p['database']}")
        click.echo(f"    Auth:     {auth_display}")
        if p.get("user"):
            click.echo(f"    User:     {p['user']}")
        click.echo()


@main.command("remove-profile")
@click.argument("name")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def cmd_remove_profile(name: str, force: bool) -> None:
    """Remove a profile by name."""
    if not force:
        if not click.confirm(f"Remove profile '{name}'?"):
            return

    if remove_profile(name):
        click.secho(f"{TICK} Profile '{name}' removed.", fg="green")
    else:
        click.secho(f"{CROSS} Profile '{name}' not found.", fg="red")
        sys.exit(1)


@main.command("set-default")
@click.argument("name")
def cmd_set_default(name: str) -> None:
    """Set the default profile."""
    if set_default_profile(name):
        click.secho(f"{TICK} Default profile set to '{name}'.", fg="green")
    else:
        click.secho(f"{CROSS} Profile '{name}' not found.", fg="red")
        sys.exit(1)


def _resolve_secret(new_value: str | None, existing_secret) -> str | None:
    """Resolve a secret field for edit-profile updates.

    Handles three cases: interactive prompt (__PROMPT__), explicit new
    value, or preserving the existing secret unchanged.
    """
    if new_value == "__PROMPT__":
        return click.prompt("New value", hide_input=True)
    if new_value:
        return new_value
    if existing_secret is not None:
        return existing_secret.get_secret_value()
    return None


@main.command("edit-profile")
@click.argument("name")
@click.option("--new-name", default=None, help="Rename the profile")
@click.option("--url", default=None, help="New Odoo URL")
@click.option("--database", default=None, help="New database name")
@click.option("--user", default=None, help="New username")
@click.option(
    "--password",
    is_flag=False,
    flag_value="__PROMPT__",
    default=None,
    help="New password (prompts if flag used without value)",
)
@click.option(
    "--api-key",
    "api_key",
    is_flag=False,
    flag_value="__PROMPT__",
    default=None,
    help="New API key for Odoo 19+ (prompts if flag used without value)",
)
@click.option("--test", "test_connection", is_flag=True, default=False, help="Test connection after editing")
def cmd_edit_profile(
    name: str,
    new_name: str,
    url: str,
    database: str,
    user: str,
    password: str,
    api_key: str,
    test_connection: bool,
) -> None:
    """Edit an existing profile.

    Only the specified fields will be updated. Use --new-name to rename,
    --password or --api-key (with or without a value) to be prompted
    for new credentials.

    Examples:
        odoo-mcp edit-profile prod --url https://new-url.com
        odoo-mcp edit-profile staging --user admin --password
        odoo-mcp edit-profile prod19 --api-key
        odoo-mcp edit-profile old-name --new-name better-name
    """
    existing = get_profile(name)
    if existing is None:
        click.secho(f"{CROSS} Profile '{name}' not found.", fg="red")
        sys.exit(1)

    new_url = url if url else existing.url
    new_database = database if database else existing.database
    new_user = user if user else existing.user

    new_password = _resolve_secret(password, existing.password)
    new_api_key = _resolve_secret(api_key, existing.api_key)

    if not new_password and not new_api_key:
        click.secho(f"{CROSS} Profile must have either a password or an api_key.", fg="red")
        sys.exit(1)

    if test_connection:
        click.echo(f"Testing connection to {new_url}...")
        try:
            if new_api_key and not new_password:
                from odoo_mcp_multi.parsers import normalize_url
                from odoo_mcp_multi.version import get_server_version

                info = get_server_version(normalize_url(new_url))
                ver = (info or {}).get("server_version", "unknown")
                click.secho(f"{TICK} Server reachable! Odoo {ver}", fg="green")
            else:
                result = op_test_connection(
                    url=new_url, database=new_database, user=new_user, password=new_password or ""
                )
                if result.get("success") is False:
                    click.secho(f"{CROSS} Connection test failed: {result['error']}", fg="red")
                    if not click.confirm("Save changes anyway?"):
                        return
                else:
                    click.secho(
                        f"{TICK} Connection successful! Authenticated as UID {result['uid']}",
                        fg="green",
                    )
        except OdooConnectionError as e:
            click.secho(f"{CROSS} Connection failed: {e}", fg="red")
            if not click.confirm("Save changes anyway?"):
                return

    effective_name = new_name if new_name and new_name != name else name

    updated_profile = OdooProfile(
        name=effective_name,
        url=new_url,
        database=new_database,
        user=new_user,
        password=new_password if new_password else None,
        api_key=new_api_key if new_api_key else None,
    )
    add_profile(updated_profile, set_default=False)

    # When renaming, remove the old profile key
    if effective_name != name:
        remove_profile(name)

    click.secho(f"{TICK} Profile '{effective_name}' updated successfully!", fg="green")


@main.command("test")
@click.option("--profile", "-p", default=None, help="Profile name to use (default: default profile)")
def cmd_test(profile: str) -> None:
    """Test connection to an Odoo instance."""
    odoo_profile = get_profile(profile)

    if odoo_profile is None and profile:
        click.secho(f"{CROSS} Profile '{profile}' not found.", fg="red")
        sys.exit(1)

    if odoo_profile is None:
        click.secho(f"{CROSS} No default profile configured. Use 'odoo-mcp add-profile' first.", fg="red")
        sys.exit(1)

    click.echo(f"Testing connection to {odoo_profile.url}...")

    try:
        _test_profile_connection(odoo_profile)
    except OdooConnectionError as e:
        click.secho(f"{CROSS} Connection failed: {e}", fg="red")
        sys.exit(1)


def _test_profile_connection(odoo_profile) -> None:
    """Run the appropriate connectivity test based on the profile's auth mode.

    Extracted to keep cmd_test focused on CLI concerns (exit codes, messages)
    while this helper owns the protocol branching.
    """
    # api_key-only profiles (Odoo 19+ JSON-2): no UID, just version probe
    if odoo_profile.api_key and not odoo_profile.password:
        from odoo_mcp_multi.parsers import normalize_url
        from odoo_mcp_multi.version import get_server_version

        info = get_server_version(normalize_url(odoo_profile.url))
        if info is None:
            raise OdooConnectionError("Could not reach server (no version info)")
        ver = info.get("server_version", info.get("version", "unknown"))
        click.secho(f"{TICK} Server reachable! Odoo {ver} [auth: api_key / JSON-2]", fg="green")
        click.echo("  Protocol: json2s")
        return

    # Legacy password auth — full authenticate round-trip
    result = op_test_connection(
        url=odoo_profile.url,
        database=odoo_profile.database,
        user=odoo_profile.user,
        password=odoo_profile.password,
        protocol=odoo_profile.protocol,
    )
    if result.get("success") is False:
        click.secho(f"{CROSS} Connection test failed: {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"{TICK} Connection successful! Authenticated as UID {result['uid']}", fg="green")
    click.echo(f"  Server version: {result['server_version']}")
    click.echo(f"  Protocol: {result['protocol']}")


@main.command("run")
@click.option("--profile", "-p", default=None, help="Fallback profile name to use (default: default profile)")
def cmd_run(profile: str) -> None:
    """Start the MCP server.

    Starts the MCP server using stdio transport for communication with Claude/Cursor.
    If a profile is provided (or a default exists), it will be used as the fallback
    when tool calls don't specify a target profile.
    """
    from odoo_mcp_multi.server import run_server, set_profile

    # Attempt to load the profile (this will return None if no profile exists or name is wrong)
    odoo_profile = get_profile(profile)

    if profile and odoo_profile is None:
        # The user explicitly asked for a profile that doesn't exist
        click.secho(f"{CROSS} Profile '{profile}' not found.", fg="red", err=True)
        sys.exit(1)

    if odoo_profile:
        # Set the fallback profile for the server
        set_profile(odoo_profile)
        click.echo(f"Starting MCP server with fallback profile '{odoo_profile.name}'...", err=True)
        click.echo(f"  URL: {odoo_profile.url}", err=True)
        click.echo(f"  Database: {odoo_profile.database}", err=True)
        click.echo(f"  User: {odoo_profile.user}", err=True)
    else:
        # No explicit or default profile, start anyway for dynamic resolution
        click.echo("Starting MCP server without a fallback profile.", err=True)
        click.echo("Tools MUST specify a 'profile' argument to execute actions.", err=True)

    # Run the server
    run_server()


# ---------------------------------------------------------------------------
# Odoo data operation commands (mirroring MCP tools)
# ---------------------------------------------------------------------------


@main.command("search-read")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--domain", "-d", default="[]", help="Search domain as string (e.g., \"[('name','ilike','John')]\")")
@click.option("--fields", "-f", default="", help="Comma-separated field names (e.g., 'name,email,phone')")
@click.option("--limit", "-l", default=100, type=int, help="Maximum number of records (default: 100)")
@click.option("--offset", default=0, type=int, help="Number of records to skip (default: 0)")
@click.option("--order", default="", help="Sort order (e.g., 'name asc, id desc')")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_search_read(model, domain, fields, limit, offset, order, profile) -> None:
    """Search and read records from an Odoo model."""
    _output(op_search_read(model, domain, fields, limit, offset, order, profile))


@main.command("write")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--ids", "-i", required=True, help="Record IDs as JSON array or comma-separated (e.g., '1,2,3')")
@click.option("--values", "-v", required=True, help="Field values as JSON object")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_write(model, ids, values, profile) -> None:
    """Update existing records in Odoo."""
    _output(op_write(model, ids, values, profile))


@main.command("unlink")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--ids", "-i", required=True, help="Record IDs as JSON array or comma-separated (e.g., '1,2,3')")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_unlink(model, ids, profile) -> None:
    """Delete records from an Odoo model."""
    _output(op_unlink(model, ids, profile))


@main.command("create")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--values", "-v", required=True, help="Field values as JSON object")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_create(model, values, profile) -> None:
    """Create a new record in Odoo."""
    _output(op_create(model, values, profile))


@main.command("export-records")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--domain", "-d", default="[]", help="Search domain as string")
@click.option("--fields", "-f", default="id,name", help="Comma-separated field names (e.g., 'id,name,country_id/id')")
@click.option("--limit", "-l", default=500, type=int, help="Maximum number of records to export (default: 500)")
@click.option("--offset", default=0, type=int, help="Number of records to skip for pagination (default: 0)")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_export_records(model, domain, fields, limit, offset, profile) -> None:
    """Export records using native export_data."""
    _output(op_export_records(model, domain, fields, limit, offset, profile))


@main.command("import-records")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--fields", "-f", required=True, help="Comma-separated field names (e.g., 'id,name')")
@click.option("--rows", "-r", required=True, help="JSON array of dictionaries with import data")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_import_records(model, fields, rows, profile) -> None:
    """Import records using native load."""
    _output(op_import_records(model, fields, rows, profile))


@main.command("execute-kw")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--method", required=True, help="Method name to execute (e.g., 'action_confirm')")
@click.option("--args", "-a", default="[]", help="Positional args as JSON array (e.g., '[[42]]')")
@click.option("--kwargs", "-k", default="{}", help="Keyword args as JSON object")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_execute_kw(model, method, args, kwargs, profile) -> None:
    """Execute any method on an Odoo model."""
    _output(op_execute_kw(model, method, args, kwargs, profile))


@main.command("get-version")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_get_version(profile) -> None:
    """Get the Odoo server version information."""
    _output(op_get_version(profile))


@main.command("list-models")
@click.option("--search", "-s", default="", help="Search term to filter model names")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_list_models(search, profile) -> None:
    """List available models in the Odoo instance."""
    _output(op_list_models(search, profile))


@main.command("list-fields")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_list_fields(model, profile) -> None:
    """List all fields of an Odoo model."""
    _output(op_list_fields(model, profile))


# ---------------------------------------------------------------------------
# Skills management commands
# ---------------------------------------------------------------------------

AGENT_DIRS = {
    "gemini": "~/.gemini/skills",
    "antigravity": "~/.gemini/antigravity/skills",
    "claude": "~/.claude/skills",
    "codex": "~/.codex/skills",
    "opencode": "~/.opencode/skills",
}


@main.group("skills", invoke_without_command=True)
@click.pass_context
def cmd_skills(ctx: click.Context) -> None:
    """Manage agentic skills provided by odoo-mcp.

    If no subcommand is provided, this defaults to listing all available skills.
    Use 'odoo-mcp skills install <agent>' to link skills into your preferred IDE.
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(cmd_skills_list)


@cmd_skills.command("list")
def cmd_skills_list() -> None:
    """List available skills bundled with odoo-mcp."""
    skills_dir = Path(__file__).parent / "skills"
    if not skills_dir.exists():
        click.secho("No skills found in the package.", fg="yellow")
        return

    click.echo("Available skills in odoo-mcp:")
    for item in sorted(skills_dir.iterdir()):
        if item.is_dir() and (item / "SKILL.md").exists():
            click.echo(f"  - {item.name}")


@cmd_skills.command("install")
@click.argument("agent", type=click.Choice(list(AGENT_DIRS.keys())))
@click.option("--force", is_flag=True, help="Overwrite existing symlinks")
def cmd_skills_install(agent: str, force: bool) -> None:
    """Install skills to the specified agentic IDE via symbolic link."""
    target_dir_str = AGENT_DIRS.get(agent)
    if not target_dir_str:
        click.secho(f"{CROSS} Unknown agent: {agent}", fg="red", err=True)
        sys.exit(1)

    target_dir = Path(target_dir_str).expanduser()
    skills_dir = Path(__file__).parent / "skills"

    if not skills_dir.exists() or not any(skills_dir.iterdir()):
        click.secho(f"{CROSS} No skills found to install.", fg="red", err=True)
        sys.exit(1)

    # Ensure target directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Installing skills for {agent} into {target_dir}...")

    linked = 0
    failed = 0
    skipped = 0
    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir() or not (item / "SKILL.md").exists():
            continue

        dest = target_dir / item.name

        if (dest.exists() or dest.is_symlink()) and not force:
            click.secho(f"  - Skipping {item.name}: already exists. Use --force to overwrite.", fg="yellow")
            skipped += 1
            continue

        if dest.exists() or dest.is_symlink():
            dest.unlink()

        try:
            dest.symlink_to(item.absolute())
            click.secho(f"  {TICK} Linked {item.name}", fg="green")
            linked += 1
        except Exception as e:
            click.secho(f"  {CROSS} Failed to link {item.name}: {e}", fg="red", err=True)
            failed += 1

    if failed:
        click.secho(
            f"\n{CROSS} Completed with errors: {linked} linked, {failed} failed, {skipped} skipped.",
            fg="red",
        )
        sys.exit(1)
    else:
        msg = f"\n{TICK} Skills successfully installed for {agent}! ({linked} linked, {skipped} skipped)"
        click.secho(msg, fg="green")


if __name__ == "__main__":
    main()

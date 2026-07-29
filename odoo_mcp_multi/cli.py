"""Click CLI for odoo-mcp-multi.

Provides commands for managing Odoo profiles and running the MCP server,
plus all Odoo data operations (search, write, create, etc.) mirroring
the MCP tool interface. Both interfaces share logic via operations.py.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
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
    op_get_financial_report,
    op_get_version,
    op_import_records,
    op_list_fields,
    op_list_models,
    op_search_count,
    op_search_read,
    op_test_connection,
    op_unlink,
    op_write,
)


def _echo_pagination_header(data: dict) -> None:
    """Print pagination metadata as a comment line when available.

    Emits a single # line with record counts and continuation offsets —
    everything an agent needs to decide whether to paginate without
    parsing JSON.
    """
    parts = []
    total = data.get("total")
    if total is not None:
        shown = data.get("limit", "?")
        parts.append(f"{shown} of {total}")
    if data.get("has_more"):
        parts.append(f"has_more=true next_offset={data.get('next_offset', '?')}")
    if not parts:
        return
    click.echo(f"# {' | '.join(parts)}")


def _output(data) -> None:
    """Emit operation results in the format that was requested.

    Non-JSON formats (table, csv, html) are printed directly — no JSON
    wrapping. JSON format retains the full envelope. Errors go to stderr
    with exit code 1.
    """
    # Non-dict payloads (e.g. list from list_profiles) → straight JSON
    if not isinstance(data, dict):
        click.echo(json.dumps(data, indent=2, default=str, ensure_ascii=False))
        return

    if data.get("success") is False:
        click.echo(f"ERROR: {data.get('error', 'Unknown error')}", err=True)
        raise SystemExit(1)

    fmt = data.get("format")

    # String-based formats — print the payload as-is
    if fmt in ("table", "csv", "html") and "data" in data:
        _echo_pagination_header(data)
        click.echo(data["data"])
        return

    # Compact — headers + rows without envelope overhead
    if fmt == "compact" and "headers" in data:
        _echo_pagination_header(data)
        click.echo(
            json.dumps(
                {"headers": data["headers"], "rows": data["rows"]},
                default=str,
                ensure_ascii=False,
            )
        )
        return

    # Everything else: json-format envelopes, write/create results, etc.
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


def _prompt_wizard_credential(
    user: str | None,
    password: str | None,
    api_key: str | None,
    protocol: str,
) -> tuple[str | None, str | None, str | None]:
    """Prompt for missing username and credentials in interactive TTY wizard."""
    if password or api_key:
        return user, password, api_key

    if not sys.stdin.isatty():
        click.secho(
            f"{CROSS} Provide either --password (legacy) or --api-key (Odoo 19+).",
            fg="red",
        )
        raise SystemExit(1)

    if protocol == "json2s":
        api_val = click.prompt("API key (Odoo 19+ Bearer token)", hide_input=True)
        return user, None, api_val

    # For auto/legacy protocols, prompt for username if not provided
    if not user:
        user = click.prompt("Odoo username (leave empty for API Key auth >19.0)", default="", show_default=False)

    # Prompt for credential
    cred_prompt = "Password" if user else "Password (or API key for Odoo 19+)"
    cred_val = click.prompt(cred_prompt, hide_input=True)

    if user:
        return user, cred_val, None

    return None, None, cred_val


@main.command("add-profile")
@click.option("--name", prompt="Profile name", help="Unique identifier (e.g., 'prod', 'staging')")
@click.option("--url", prompt="Odoo URL", help="Instance URL (e.g., 'https://odoo.example.com')")
@click.option("--database", prompt="Database name", help="Odoo database name")
@click.option("--user", default=None, help="Odoo username (legacy auth, Odoo < 19)")
@click.option("--password", default=None, hide_input=True, help="Odoo password (legacy auth, Odoo < 19)")
@click.option("--api-key", "api_key", default=None, help="API key for Odoo 19+ Bearer auth (/json/2)")
@click.option("--protocol", default="auto", help="RPC protocol: auto, json2s, jsonrpcs, xmlrpcs (default: auto)")
@click.option("--verify/--no-verify", "verify", default=True, help="Verify SSL certificates (default: True)")
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
    verify: bool,
    set_default: bool,
    test_connection: bool,
) -> None:
    """Add a new Odoo profile with credentials."""
    user, password, api_key = _prompt_wizard_credential(user, password, api_key, protocol)

    if test_connection:
        click.echo(f"Testing connection to {url}...")
        res = op_test_connection(
            url=url,
            database=database,
            user=user or "",
            password=password or "",
            api_key=api_key or "",
            protocol=protocol if protocol != "auto" else None,
            verify=verify,
        )
        if res.get("success") is False:
            click.secho(f"{CROSS} Connection test failed: {res.get('error')}", fg="red")
            if not click.confirm("Save profile anyway?"):
                return
        else:
            uid_info = f"Authenticated as UID {res['uid']}" if "uid" in res else "Server reachable"
            click.secho(f"{TICK} Connection successful! {uid_info}", fg="green")
            # Auto-migrate password -> api_key if server was detected as Odoo 19+ (JSON2S)
            if res.get("protocol") == "json2s" and password and not api_key:
                api_key, password = password, None

    profile = OdooProfile(
        name=name,
        url=url,
        database=database,
        user=user or "",
        password=password if password else None,
        api_key=api_key if api_key else None,
        protocol=protocol,
        verify=verify,
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
        click.echo(f"    Verify:   {p.get('verify', True)}")
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
@click.option(
    "--verify/--no-verify",
    "verify",
    default=None,
    help="Update SSL certificate verification setting",
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
    verify: bool | None,
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
    new_verify = verify if verify is not None else existing.verify

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

                info = get_server_version(normalize_url(new_url), verify=new_verify)
                ver = (info or {}).get("server_version", "unknown")
                click.secho(f"{TICK} Server reachable! Odoo {ver}", fg="green")
            else:
                result = op_test_connection(
                    url=new_url, database=new_database, user=new_user, password=new_password or "", verify=new_verify
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
        verify=new_verify,
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
    from odoo_mcp_multi.server import _set_fallback_ref, run_server, set_profile

    # Attempt to load the profile (this will return None if no profile exists or name is wrong)
    odoo_profile = get_profile(profile)

    if profile and odoo_profile is None:
        # The user explicitly asked for a profile that doesn't exist
        click.secho(f"{CROSS} Profile '{profile}' not found.", fg="red", err=True)
        sys.exit(1)

    if odoo_profile:
        # Set the fallback profile for the server
        set_profile(odoo_profile)
        _set_fallback_ref(odoo_profile)
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
@click.option("--limit", "-l", default=25, type=int, help="Maximum number of records (default: 25)")
@click.option("--offset", default=0, type=int, help="Number of records to skip (default: 0)")
@click.option("--order", default="", help="Sort order (e.g., 'name asc, id desc')")
@click.option(
    "--format",
    "-F",
    "fmt",
    default="json",
    type=click.Choice(["json", "compact", "table", "html", "csv"], case_sensitive=False),
    help="Output format: json (default), compact, table, html, or csv",
)
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_search_read(model, domain, fields, limit, offset, order, fmt, profile) -> None:
    """Search and read records from an Odoo model."""
    _output(op_search_read(model, domain, fields, limit, offset, order, fmt, profile))


@main.command("search-count")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--domain", "-d", default="[]", help="Search domain as string (e.g., \"[('name','ilike','John')]\")")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_search_count(model, domain, profile) -> None:
    """Count records matching a domain without fetching data."""
    _output(op_search_count(model, domain, profile))


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
@click.option(
    "--format",
    "-F",
    "fmt",
    default="json",
    type=click.Choice(["json", "compact", "table", "html", "csv"], case_sensitive=False),
    help="Output format: json (default), compact, table, html, or csv",
)
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_export_records(model, domain, fields, limit, offset, fmt, profile) -> None:
    """Export records using native export_data."""
    _output(op_export_records(model, domain, fields, limit, offset, fmt, profile))


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
@click.option(
    "--format",
    "-F",
    "fmt",
    default="json",
    type=click.Choice(["json", "compact", "table", "html", "csv"], case_sensitive=False),
    help="Output format: json (default), compact, table, html, or csv",
)
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_list_models(search, fmt, profile) -> None:
    """List available models in the Odoo instance."""
    _output(op_list_models(search, fmt, profile))


@main.command("list-fields")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option(
    "--format",
    "-F",
    "fmt",
    default="json",
    type=click.Choice(["json", "compact", "table", "html", "csv"], case_sensitive=False),
    help="Output format: json (default), compact, table, html, or csv",
)
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_list_fields(model, fmt, profile) -> None:
    """List all fields of an Odoo model."""
    _output(op_list_fields(model, format=fmt, profile=profile))


# ---------------------------------------------------------------------------
# Plugins & Skills management commands
# ---------------------------------------------------------------------------

# "agents" is the cross-agent standard location (agentskills.io), read
# natively by Codex, AGY, OpenCode, Kimi and Hermes. "agy" installs
# standalone skills into the Antigravity global skills directory
# (recognized by AGY, AGY CLI and AGY IDE), while "antigravity"
# installs the full plugin (manifest + skills).
AGENT_DIRS = {
    "agents": "~/.agents/skills",
    "antigravity": "~/.gemini/config/plugins",
    "agy": "~/.gemini/config/skills",
    "claude": "~/.claude/skills",
    "codex": "~/.agents/skills",
    "opencode": "~/.config/opencode/skills",
    "kimi": "~/.kimi/skills",
    "hermes": "~/.hermes/skills",
}


def _get_plugin_dir() -> Path:
    return Path(__file__).parent / "plugins" / "odoo-mcp"


def _get_skills_dir() -> Path:
    return _get_plugin_dir() / "skills"


# Strictest published cross-agent constraints: OpenCode requires the
# frontmatter name to equal the directory name and match this pattern;
# OpenCode and Kimi cap description at 1024 chars.
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SKILL_DESCRIPTION_MAX = 1024


def _read_frontmatter(skill_md: Path) -> dict:
    """Parse the flat key/value frontmatter block of a SKILL.md file."""
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            data[key.strip()] = value.strip().strip("\"'")
    return data


def _validate_skill(item: Path) -> list[str]:
    """Return contract warnings for a skill directory's SKILL.md frontmatter."""
    frontmatter = _read_frontmatter(item / "SKILL.md")
    warnings = []

    name = frontmatter.get("name", "")
    if not name:
        warnings.append("missing 'name' in frontmatter")
    elif name != item.name:
        warnings.append(f"frontmatter name '{name}' differs from directory name '{item.name}'")
    elif not SKILL_NAME_RE.fullmatch(name):
        warnings.append(f"name '{name}' violates the ^[a-z0-9]+(-[a-z0-9]+)*$ pattern")

    description = frontmatter.get("description", "")
    if not description:
        warnings.append("missing 'description' in frontmatter")
    elif len(description) > SKILL_DESCRIPTION_MAX:
        warnings.append(f"description exceeds {SKILL_DESCRIPTION_MAX} chars ({len(description)})")

    return warnings


def _warn_skill_contract_violations(skills_dir: Path) -> None:
    """Print frontmatter contract warnings without blocking the install."""
    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir() or not (item / "SKILL.md").exists():
            continue
        for warning in _validate_skill(item):
            click.secho(f"  ! {item.name}: {warning}", fg="yellow")


def _remove_existing(dest: Path) -> None:
    """Remove a previously installed symlink, file, or copied directory."""
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.is_dir():
        shutil.rmtree(dest)


def _install_item(item: Path, dest: Path, force: bool, symlink: bool) -> tuple[int, int, int]:
    """Install a single file or directory by copy (default) or symlink.

    Copying is the default because symlinks are not discovered by the
    Antigravity IDE, require elevated privileges on Windows, and dangle
    when an editable install lives in a temporary git worktree. Returns
    (installed, failed, skipped) counts for aggregation.
    """
    if (dest.exists() or dest.is_symlink()) and not force:
        click.secho(f"  - Skipping {dest.name}: already exists. Use --force to overwrite.", fg="yellow")
        return (0, 0, 1)

    try:
        if dest.exists() or dest.is_symlink():
            _remove_existing(dest)
        if symlink:
            dest.symlink_to(item.absolute())
        elif item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
        verb = "Linked" if symlink else "Copied"
        click.secho(f"  {TICK} {verb} {dest.name}", fg="green")
        return (1, 0, 0)
    except OSError as e:
        click.secho(f"  {CROSS} Failed to install {dest.name}: {e}", fg="red", err=True)
        return (0, 1, 0)


def _install_antigravity_plugin(
    plugin_dir: Path, skills_dir: Path, target_dir: Path, force: bool, symlink: bool
) -> tuple[int, int, int]:
    """Install plugin.json plus every skill into the Antigravity plugin tree."""
    target_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"Installing plugin for antigravity into {target_dir}...")

    installed, failed, skipped = 0, 0, 0

    plugin_json = plugin_dir / "plugin.json"
    if plugin_json.exists():
        inst_cnt, fail_cnt, skip_cnt = _install_item(plugin_json, target_dir / "plugin.json", force, symlink)
        installed += inst_cnt
        failed += fail_cnt
        skipped += skip_cnt

    target_skills_dir = target_dir / "skills"
    target_skills_dir.mkdir(parents=True, exist_ok=True)

    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir() or not (item / "SKILL.md").exists():
            continue
        inst_cnt, fail_cnt, skip_cnt = _install_item(item, target_skills_dir / item.name, force, symlink)
        installed += inst_cnt
        failed += fail_cnt
        skipped += skip_cnt

    return installed, failed, skipped


def _install_flat_skills(
    agent: str, skills_dir: Path, target_dir: Path, force: bool, symlink: bool
) -> tuple[int, int, int]:
    """Install bare skill directories for agents without a plugin manifest."""
    target_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"Installing skills for {agent} into {target_dir}...")

    installed, failed, skipped = 0, 0, 0
    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir() or not (item / "SKILL.md").exists():
            continue
        inst_cnt, fail_cnt, skip_cnt = _install_item(item, target_dir / item.name, force, symlink)
        installed += inst_cnt
        failed += fail_cnt
        skipped += skip_cnt

    return installed, failed, skipped


def _report_installation_result(agent: str, installed: int, failed: int, skipped: int) -> None:
    """Print the aggregate install summary and exit non-zero on failures."""
    if failed:
        click.secho(
            f"\n{CROSS} Completed with errors: {installed} installed, {failed} failed, {skipped} skipped.",
            fg="red",
        )
        sys.exit(1)

    click.secho(
        f"\n{TICK} Successfully installed for {agent}! ({installed} installed, {skipped} skipped)",
        fg="green",
    )


def _install_plugin_or_skills(agent: str, force: bool, symlink: bool = False) -> None:
    """Shared driver for plugins/skills install across all supported agents."""
    target_dir_str = AGENT_DIRS.get(agent)
    if not target_dir_str:
        click.secho(f"{CROSS} Unknown agent: {agent}", fg="red", err=True)
        sys.exit(1)

    plugin_dir = _get_plugin_dir()
    skills_dir = _get_skills_dir()

    if not skills_dir.exists() or not any(skills_dir.iterdir()):
        click.secho(f"{CROSS} No skills found to install.", fg="red", err=True)
        sys.exit(1)

    _warn_skill_contract_violations(skills_dir)

    target_dir = Path(target_dir_str).expanduser()

    if agent == "antigravity":
        # The plugin directory name is the single source of the plugin id.
        target_dir = target_dir / plugin_dir.name
        installed, failed, skipped = _install_antigravity_plugin(plugin_dir, skills_dir, target_dir, force, symlink)
        _report_installation_result(agent, installed, failed, skipped)
        return

    installed, failed, skipped = _install_flat_skills(agent, skills_dir, target_dir, force, symlink)
    _report_installation_result(agent, installed, failed, skipped)


@main.group("plugins", invoke_without_command=True)
@click.pass_context
def cmd_plugins(ctx: click.Context) -> None:
    """Manage agentic plugins provided by odoo-mcp (alias: skills)."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(cmd_plugins_list)


def _list_plugins_and_skills() -> None:
    skills_dir = _get_skills_dir()
    if not skills_dir.exists():
        click.secho("No skills/plugins found in the package.", fg="yellow")
        return

    click.echo("Available skills in odoo-mcp plugin:")
    for item in sorted(skills_dir.iterdir()):
        if item.is_dir() and (item / "SKILL.md").exists():
            click.echo(f"  - {item.name}")


@cmd_plugins.command("list")
def cmd_plugins_list() -> None:
    """List available plugins and skills bundled with odoo-mcp."""
    _list_plugins_and_skills()


@cmd_plugins.command("install")
@click.argument("agent", type=click.Choice(list(AGENT_DIRS.keys())))
@click.option("--force", is_flag=True, help="Overwrite existing installed files")
@click.option(
    "--symlink",
    is_flag=True,
    help="Symlink into the package instead of copying (dev mode; not discovered by Antigravity IDE)",
)
def cmd_plugins_install(agent: str, force: bool, symlink: bool) -> None:
    """Install plugin and skills for the specified agentic IDE.

    Files are copied by default so the install works on Windows, inside
    the Antigravity IDE, and survives package relocation. Use --symlink
    to link into the package source while developing; re-run with
    --force after upgrading to refresh copied files.
    """
    _install_plugin_or_skills(agent, force, symlink)


def _uninstall_plugin_or_skills(agent: str) -> None:
    """Remove installed plugin/skill files (copies or symlinks) for an agent."""
    target_dir_str = AGENT_DIRS.get(agent)
    if not target_dir_str:
        click.secho(f"{CROSS} Unknown agent: {agent}", fg="red", err=True)
        sys.exit(1)

    target_dir = Path(target_dir_str).expanduser()

    # The antigravity target is a plugin directory owned entirely by
    # odoo-mcp, so it is removed as a whole.
    if agent == "antigravity":
        target_dir = target_dir / _get_plugin_dir().name
        if not target_dir.exists() and not target_dir.is_symlink():
            click.echo(f"Nothing to uninstall for {agent} ({target_dir} not found).")
            return
        _remove_existing(target_dir)
        click.secho(f"{TICK} Removed {target_dir}", fg="green")
        return

    # Flat agents share their skills directory with other packages —
    # remove only the skills bundled with odoo-mcp.
    removed = 0
    for item in sorted(_get_skills_dir().iterdir()):
        if not item.is_dir() or not (item / "SKILL.md").exists():
            continue
        dest = target_dir / item.name
        if dest.exists() or dest.is_symlink():
            _remove_existing(dest)
            click.secho(f"  {TICK} Removed {dest.name}", fg="green")
            removed += 1

    if removed:
        click.secho(f"\n{TICK} Uninstalled {removed} skill(s) for {agent}.", fg="green")
    else:
        click.echo(f"Nothing to uninstall for {agent} in {target_dir}.")


@cmd_plugins.command("uninstall")
@click.argument("agent", type=click.Choice(list(AGENT_DIRS.keys())))
def cmd_plugins_uninstall(agent: str) -> None:
    """Remove installed plugin and skills for the specified agentic IDE."""
    _uninstall_plugin_or_skills(agent)


# Historic entry point kept as a true alias: both names expose the exact
# same group object, so subcommands and options can never drift apart.
main.add_command(cmd_plugins, name="skills")


# ---------------------------------------------------------------------------
# Self-update command
# ---------------------------------------------------------------------------

PACKAGE_NAME = "odoo-mcp-multi"


def _detect_install_context() -> str:
    """Determine how odoo-mcp-multi was installed.

    Returns one of 'editable', 'pipx', or 'pip' so the upgrade command
    can invoke the right tool without cross-contaminating environments.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", PACKAGE_NAME],
        capture_output=True,
        text=True,
    )
    if "Editable project location" in result.stdout:
        return "editable"
    if "pipx" in sys.executable:
        return "pipx"
    return "pip"


def _run_upgrade_command(cmd: list[str]) -> tuple[int, str]:
    """Execute an upgrade subprocess and return (exit_code, output)."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr).strip()


@main.command("get-financial-report")
@click.option("--report", "-r", required=True, help="Report ID, XML ID, or exact report name")
@click.option("--date-from", "--df", default=None, help="Start date (YYYY-MM-DD) for range-based calculations")
@click.option("--date-to", "--dt", default=None, help="End date (YYYY-MM-DD) for calculations")
@click.option("--date-filter", "--dfilt", default=None, help="Preset date filter (e.g., 'today', 'this_month')")
@click.option(
    "--format",
    "-f",
    "fmt",
    default="json",
    type=click.Choice(["json", "table", "html", "csv"], case_sensitive=False),
    help="Output format: json (default), table (markdown), html, or csv",
)
@click.option("--profile", "-p", default=None, help="Profile name to use")
@click.option(
    "--company-ids",
    "--cids",
    default=None,
    help="Comma-separated company IDs (e.g. '19,1') to calculate the report for",
)
def cmd_get_financial_report(report, date_from, date_to, date_filter, fmt, profile, company_ids) -> None:
    """Calculate and format an Odoo financial report.

    Designed, validated, and explicitly compatible with Odoo 17.0, 18.0, and 19.0+.
    At runtime, Odoo version compatibility is validated:
    - Odoo 17.0 and 18.0: The reporting engine dynamically uses the plural 'get_report_informations'
      method. Option schemas and field definitions are fully supported and validated.
    - Odoo 19.0+: Uses the singular 'get_report_information' method.
    - Odoo < 17.0: Unsupported; returns a validation error.
    """
    _output(
        op_get_financial_report(
            report_id_or_name=report,
            date_from=date_from,
            date_to=date_to,
            date_filter=date_filter,
            format=fmt,
            profile=profile,
            company_ids=company_ids,
        )
    )


@main.command("upgrade")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force upgrade even on editable installs.",
)
def cmd_upgrade(force) -> None:
    """Self-update odoo-mcp-multi to the latest version.

    Detects the installation method (pip, pipx, or editable) and runs
    the appropriate upgrade command. Editable installs are skipped
    unless --force is passed.
    """
    current_version = __version__
    context = _detect_install_context()

    click.echo(f"Current version: {current_version}")
    click.echo(f"Install context: {context}")

    if context == "editable" and not force:
        click.secho(
            "Editable install detected. Use 'git pull' + 'pip install -e .' "
            "to update, or pass --force to upgrade from PyPI anyway.",
            fg="yellow",
        )
        return

    pip_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE_NAME]
    upgrade_commands = {
        "editable": pip_cmd,
        "pip": pip_cmd,
        "pipx": ["pipx", "upgrade", PACKAGE_NAME],
    }
    cmd = upgrade_commands[context]

    click.echo(f"Running: {' '.join(cmd)}")
    exit_code, output = _run_upgrade_command(cmd)

    if exit_code != 0:
        click.secho(f"Upgrade failed (exit {exit_code}):\n{output}", fg="red", err=True)
        sys.exit(1)

    if "already satisfied" in output.lower() or "already up" in output.lower():
        click.secho(
            f"{TICK} Already at the latest version ({current_version}).",
            fg="green",
        )
        return

    click.secho(f"{TICK} Upgrade successful!\n{output}", fg="green")


if __name__ == "__main__":
    main()

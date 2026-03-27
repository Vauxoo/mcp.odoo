"""Click CLI for odoo-mcp-multi.

Provides commands for managing Odoo profiles and running the MCP server,
plus all Odoo data operations (search, write, create, etc.) mirroring
the MCP tool interface. Both interfaces share logic via operations.py.
"""

from __future__ import annotations

import json
import sys

import click

from odoo_mcp_multi import __version__
from odoo_mcp_multi.config import (
    OdooProfile,
    add_profile,
    get_profile,
    list_profiles,
    remove_profile,
    set_default_profile,
)
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
    op_write,
)
from odoo_mcp_multi.utils import (
    OdooAuthenticationError,
    OdooConnectionError,
    OdooExecutionError,
)


def _output(data, as_json: bool = True) -> None:
    """Output data as formatted JSON to stdout."""
    click.echo(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def _handle_error(e: Exception) -> None:
    """Print error and exit with code 1."""
    click.secho(f"✗ Error: {e}", fg="red", err=True)
    sys.exit(1)


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
@click.option("--user", prompt="Username", help="Odoo username")
@click.option("--password", prompt="Password", hide_input=True, help="Odoo password")
@click.option("--default", "set_default", is_flag=True, help="Set as default profile")
@click.option("--test", "test_connection", is_flag=True, default=True, help="Test connection before saving")
def cmd_add_profile(
    name: str,
    url: str,
    database: str,
    user: str,
    password: str,
    set_default: bool,
    test_connection: bool,
) -> None:
    """Add a new Odoo profile with credentials.

    Starts an interactive wizard to collect Odoo connection details.
    Optionally tests the connection before saving.
    """
    if test_connection:
        click.echo(f"Testing connection to {url}...")
        try:
            result = op_test_connection(url=url, database=database, user=user, password=password)
            click.secho(f"✓ Connection successful! Authenticated as UID {result['uid']}", fg="green")
        except OdooConnectionError as e:
            click.secho(f"✗ Connection failed: {e}", fg="red")
            if not click.confirm("Save profile anyway?"):
                return
        except OdooAuthenticationError as e:
            click.secho(f"✗ Authentication failed: {e}", fg="red")
            if not click.confirm("Save profile anyway?"):
                return

    profile = OdooProfile(
        name=name,
        url=url,
        database=database,
        user=user,
        password=password,
    )
    add_profile(profile, set_default=set_default)
    click.secho(f"✓ Profile '{name}' saved successfully!", fg="green")

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
        click.echo(f"  {p['name']}{default_marker}")
        click.echo(f"    URL:      {p['url']}")
        click.echo(f"    Database: {p['database']}")
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
        click.secho(f"✓ Profile '{name}' removed.", fg="green")
    else:
        click.secho(f"✗ Profile '{name}' not found.", fg="red")
        sys.exit(1)


@main.command("set-default")
@click.argument("name")
def cmd_set_default(name: str) -> None:
    """Set the default profile."""
    if set_default_profile(name):
        click.secho(f"✓ Default profile set to '{name}'.", fg="green")
    else:
        click.secho(f"✗ Profile '{name}' not found.", fg="red")
        sys.exit(1)


@main.command("edit-profile")
@click.argument("name")
@click.option("--url", default=None, help="New Odoo URL")
@click.option("--database", default=None, help="New database name")
@click.option("--user", default=None, help="New username")
@click.option(
    "--password", is_flag=False, flag_value="__PROMPT__", default=None, help="New password (prompts if flag used)"
)
@click.option("--test", "test_connection", is_flag=True, default=False, help="Test connection after editing")
def cmd_edit_profile(
    name: str,
    url: str,
    database: str,
    user: str,
    password: str,
    test_connection: bool,
) -> None:
    """Edit an existing profile.

    Only the specified fields will be updated. Use --password to be prompted
    for a new password, or provide other options directly.

    Examples:
        odoo-mcp edit-profile prod --url https://new-url.com
        odoo-mcp edit-profile staging --user admin --password
    """
    existing = get_profile(name)
    if existing is None:
        click.secho(f"✗ Profile '{name}' not found.", fg="red")
        sys.exit(1)

    # Determine new values (keep existing if not provided)
    new_url = url if url else existing.url
    new_database = database if database else existing.database
    new_user = user if user else existing.user

    # Handle password: prompt if flag used, keep existing otherwise
    if password == "__PROMPT__":
        new_password = click.prompt("New password", hide_input=True)
    elif password:
        new_password = password
    else:
        new_password = existing.password.get_secret_value()

    # Test connection if requested
    if test_connection:
        click.echo(f"Testing connection to {new_url}...")
        try:
            result = op_test_connection(url=new_url, database=new_database, user=new_user, password=new_password)
            click.secho(f"✓ Connection successful! Authenticated as UID {result['uid']}", fg="green")
        except OdooConnectionError as e:
            click.secho(f"✗ Connection failed: {e}", fg="red")
            if not click.confirm("Save changes anyway?"):
                return
        except OdooAuthenticationError as e:
            click.secho(f"✗ Authentication failed: {e}", fg="red")
            if not click.confirm("Save changes anyway?"):
                return

    # Create updated profile
    updated_profile = OdooProfile(
        name=name,
        url=new_url,
        database=new_database,
        user=new_user,
        password=new_password,
    )
    add_profile(updated_profile, set_default=False)
    click.secho(f"✓ Profile '{name}' updated successfully!", fg="green")


@main.command("test")
@click.option("--profile", "-p", default=None, help="Profile name to use (default: default profile)")
def cmd_test(profile: str) -> None:
    """Test connection to an Odoo instance."""
    odoo_profile = get_profile(profile)

    if odoo_profile is None:
        if profile:
            click.secho(f"✗ Profile '{profile}' not found.", fg="red")
        else:
            click.secho("✗ No default profile configured. Use 'odoo-mcp add-profile' first.", fg="red")
        sys.exit(1)

    click.echo(f"Testing connection to {odoo_profile.url}...")

    try:
        result = op_test_connection(
            url=odoo_profile.url,
            database=odoo_profile.database,
            user=odoo_profile.user,
            password=odoo_profile.password,
            protocol=odoo_profile.protocol,
        )
        click.secho(f"✓ Connection successful! Authenticated as UID {result['uid']}", fg="green")
        click.echo(f"  Server version: {result['server_version']}")
        click.echo(f"  Protocol: {result['protocol']}")

    except OdooConnectionError as e:
        click.secho(f"✗ Connection failed: {e}", fg="red")
        sys.exit(1)
    except OdooAuthenticationError as e:
        click.secho(f"✗ Authentication failed: {e}", fg="red")
        sys.exit(1)


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
        click.secho(f"✗ Profile '{profile}' not found.", fg="red", err=True)
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
    try:
        result = op_search_read(model, domain, fields, limit, offset, order, profile)
        _output(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError, ValueError) as e:
        _handle_error(e)


@main.command("write")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--ids", "-i", required=True, help="Record IDs as JSON array or comma-separated (e.g., '1,2,3')")
@click.option("--values", "-v", required=True, help="Field values as JSON object")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_write(model, ids, values, profile) -> None:
    """Update existing records in Odoo."""
    try:
        result = op_write(model, ids, values, profile)
        _output(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError, ValueError) as e:
        _handle_error(e)


@main.command("create")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--values", "-v", required=True, help="Field values as JSON object")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_create(model, values, profile) -> None:
    """Create a new record in Odoo."""
    try:
        result = op_create(model, values, profile)
        _output(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError, ValueError) as e:
        _handle_error(e)


@main.command("export-records")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--domain", "-d", default="[]", help="Search domain as string")
@click.option("--fields", "-f", default="id,name", help="Comma-separated field names (e.g., 'id,name,country_id/id')")
@click.option("--limit", "-l", default=500, type=int, help="Maximum number of records to export (default: 500)")
@click.option("--offset", default=0, type=int, help="Number of records to skip for pagination (default: 0)")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_export_records(model, domain, fields, limit, offset, profile) -> None:
    """Export records using native export_data."""
    try:
        result = op_export_records(model, domain, fields, limit, offset, profile)
        _output(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError, ValueError) as e:
        _handle_error(e)


@main.command("import-records")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--fields", "-f", required=True, help="Comma-separated field names (e.g., 'id,name')")
@click.option("--rows", "-r", required=True, help="JSON array of dictionaries with import data")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_import_records(model, fields, rows, profile) -> None:
    """Import records using native load."""
    try:
        result = op_import_records(model, fields, rows, profile)
        _output(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError, ValueError) as e:
        _handle_error(e)


@main.command("execute-kw")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--method", required=True, help="Method name to execute (e.g., 'action_confirm')")
@click.option("--args", "-a", default="[]", help="Positional args as JSON array (e.g., '[[42]]')")
@click.option("--kwargs", "-k", default="{}", help="Keyword args as JSON object")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_execute_kw(model, method, args, kwargs, profile) -> None:
    """Execute any method on an Odoo model."""
    try:
        result = op_execute_kw(model, method, args, kwargs, profile)
        _output(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError, ValueError) as e:
        _handle_error(e)


@main.command("get-version")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_get_version(profile) -> None:
    """Get the Odoo server version information."""
    try:
        result = op_get_version(profile)
        _output(result)
    except Exception as e:
        _handle_error(e)


@main.command("list-models")
@click.option("--search", "-s", default="", help="Search term to filter model names")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_list_models(search, profile) -> None:
    """List available models in the Odoo instance."""
    try:
        result = op_list_models(search, profile)
        _output(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        _handle_error(e)


@main.command("list-fields")
@click.option("--model", "-m", required=True, help="Model name (e.g., 'res.partner')")
@click.option("--profile", "-p", default=None, help="Profile name to use")
def cmd_list_fields(model, profile) -> None:
    """List all fields of an Odoo model."""
    try:
        result = op_list_fields(model, profile)
        _output(result)
    except (OdooConnectionError, OdooAuthenticationError, OdooExecutionError) as e:
        _handle_error(e)


if __name__ == "__main__":
    main()

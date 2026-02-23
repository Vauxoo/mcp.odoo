"""Click CLI for odoo-mcp-multi.

Provides commands for managing Odoo profiles and running the MCP server:
- add-profile: Interactive wizard to add credentials
- list-profiles: Show configured profiles
- remove-profile: Delete a profile
- run: Start the MCP server
"""

from __future__ import annotations

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
from odoo_mcp_multi.utils import (
    OdooAuthenticationError,
    OdooConnectionError,
    create_client,
    get_server_version,
)


@click.group()
@click.version_option(version=__version__, prog_name="odoo-mcp")
def main() -> None:
    """MCP Server for connecting Claude/Cursor to multiple Odoo instances.

    Use 'odoo-mcp add-profile' to configure an Odoo instance,
    then 'odoo-mcp run' to start the MCP server.
    """
    pass


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
            client = create_client(url=url, database=database, user=user, password=password, timeout=30)
            uid = client.authenticate()
            click.secho(f"✓ Connection successful! Authenticated as UID {uid}", fg="green")
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
        import json

        click.echo(json.dumps(profiles, indent=2))
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
            client = create_client(
                url=new_url, database=new_database, user=new_user, password=new_password, timeout=30
            )
            uid = client.authenticate()
            click.secho(f"✓ Connection successful! Authenticated as UID {uid}", fg="green")
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
        client = create_client(
            url=odoo_profile.url,
            database=odoo_profile.database,
            user=odoo_profile.user,
            password=odoo_profile.password,
            protocol=odoo_profile.protocol,
            timeout=30,
        )
        uid = client.authenticate()
        click.secho(f"✓ Connection successful! Authenticated as UID {uid}", fg="green")

        # Try to get version info
        version = get_server_version(odoo_profile.url)
        if version:
            click.echo(f"  Server version: {version.get('server_version', 'unknown')}")
            click.echo(f"  Protocol: {odoo_profile.protocol}")

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


if __name__ == "__main__":
    main()

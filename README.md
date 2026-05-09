# odoo-mcp-multi

<p align="center">
  <img src="https://git.vauxoo.com/nhomar/mcp.odoo/-/raw/main/docs/banner.png" alt="Odoo MCP — Talk to Odoo like Jarvis" width="100%">
</p>

[![PyPI version](https://img.shields.io/pypi/v/odoo-mcp-multi.svg)](https://pypi.org/project/odoo-mcp-multi/)
[![Python](https://img.shields.io/pypi/pyversions/odoo-mcp-multi.svg)](https://pypi.org/project/odoo-mcp-multi/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![pipeline status](https://git.vauxoo.com/nhomar/mcp.odoo/badges/main/pipeline.svg)](https://git.vauxoo.com/nhomar/mcp.odoo/-/pipelines)
[![coverage](https://git.vauxoo.com/nhomar/mcp.odoo/badges/main/coverage.svg)](https://git.vauxoo.com/nhomar/mcp.odoo/-/commits/main)

MCP server and CLI that connects AI clients (Antigravity, Claude Desktop, Cursor,
VS Code) to one or more Odoo instances. It exposes 12 tools for searching,
counting, creating, updating, deleting, exporting, and importing records through
the [Model Context Protocol](https://modelcontextprotocol.io/). No Odoo module
installation required. Works with Odoo 8.0 through 19.0+.

## What Problem Does This Solve

Other Odoo MCP servers require you to set environment variables for a single
Odoo instance. When you work with multiple environments (production, staging,
development, client instances), you must stop the server, change the variables,
and restart.

`odoo-mcp-multi` solves this with **named profiles** stored in a local config
file. Each profile holds its own URL, database, and credentials. Any tool call
or CLI command can target a different profile with a single `--profile` / `-p`
flag — no server restart, no env var juggling. The server auto-detects which
RPC protocol to use (XML-RPC for Odoo 8–18, JSON-RPC, or JSON/2 REST for
Odoo 19+) based on the target instance version.

Every MCP tool is also available as a CLI command with identical logic and
output format. This means you can script Odoo operations in bash, pipe JSON
through `jq`, and automate workflows without writing Python.

## Features

- **Multi-profile management** — store credentials for `prod`, `staging`, `dev` (or any name) and switch with `-p`
- **Auto protocol detection** — XML-RPC (8.0+), JSON-RPC, JSON/2 REST (19.0+) selected automatically per profile
- **Secure credential storage** — `~/.config/odoo-mcp/profiles.json` with Unix `600` permissions (owner-read-only)
- **12 MCP tools** — `search_read`, `search_count`, `write`, `unlink`, `create`, `export_records`, `import_records`, `execute_kw`, `list_models`, `list_fields`, `list_available_profiles`, `get_version`
- **Full CLI parity** — every MCP tool works as a terminal command with JSON output, composable with `jq` and shell scripts
- **Agentic skills** — ships two installable skill files for AI agents (`odoo-mcp skills install <agent>`)
- **No Odoo module required** — connects through standard XML-RPC or the native `/json/2` REST API

## How It Differs From Other Odoo MCP Servers

| Capability | `odoo-mcp-multi` | `mcp-odoo` (tuanle96) | `mcp-server-odoo` (ivnvxd) |
|---|---|---|---|
| Multiple Odoo instances in one session | Named profiles, switch per-call | One instance per env-var set | One instance per env-var set |
| Credential storage | Persistent file, `600` perms | Environment variables | Environment variables / `.env` |
| Protocol detection | Automatic (XML-RPC / JSON-RPC / JSON/2) | Manual `ODOO_TRANSPORT` flag | XML-RPC only (YOLO mode) |
| Odoo-side module required | No | No | Optional (recommended for prod) |
| CLI with identical logic | Full parity (all 12 operations) | No CLI | No CLI |
| Native `export_data` / `load` | `export_records` / `import_records` | No | No |
| Agentic skills shipped | 2 installable skills | No | No |
| Odoo 19+ JSON/2 REST support | Automatic with API key | Manual config | No |
| Package distribution | PyPI (`pip install odoo-mcp-multi`) | PyPI (`pip install odoo-mcp`) | PyPI (`pip install mcp-server-odoo`) |

## 1-Minute Setup (Copy-Paste Prompts)

Paste the blocks below into your AI client (Antigravity, Claude, Cursor) to get started.

### 1. Install the Package

```text
Please install the `odoo-mcp-multi` package. Use the best method for my OS:
- macOS: `brew install pipx && pipx install odoo-mcp-multi`
- Linux: `pip install pipx && pipx install odoo-mcp-multi`
- Windows: `winget install Python.Python.3.12`, then `pip install pipx && pipx ensurepath`, then `pipx install odoo-mcp-multi`
- Or simply use `pip install odoo-mcp-multi` if a python environment is already managed.

After installing, please run `odoo-mcp add-profile` to configure my credentials interactively, and then run `odoo-mcp test` to verify the connection.
```

### 2. Configure MCP

```text
Please configure the `odoo-mcp` server in my MCP client settings.
Add the following block to my configuration file (e.g. `mcp_config.json` for Antigravity, or `claude_desktop_config.json` for Claude):

{
  "mcpServers": {
    "odoo": {
      "command": "odoo-mcp",
      "args": ["run"]
    }
  }
}

Once added, remind me to restart my AI client so I can use the 11 Odoo tools available.
```

### 3. Install Agentic Skills

```text
Please install the agentic skills bundled with the `odoo-mcp` package.
Run the command `odoo-mcp skills install <agent_name>` where `<agent_name>` is your own identity (e.g., `gemini`, `antigravity`, `claude`, `codex`, or `opencode`).
This will automatically symlink the skills into my global skills directory so you can use them in future tasks.
```

## Installation

`pipx` is the recommended installer for all platforms — it creates an
isolated virtual environment and exposes `odoo-mcp` globally.

### macOS

```bash
brew install pipx
pipx install odoo-mcp-multi
odoo-mcp add-profile
odoo-mcp run
```

### Linux

```bash
pip install pipx
pipx install odoo-mcp-multi
odoo-mcp add-profile
odoo-mcp run
```

### Windows

> **Pre-requisite:** Python must be installed before pipx.
> The recommended method is `winget` (included in Windows 10 21H1+ and Windows 11):

```powershell
# Step 1: Install Python via winget (opens a new PowerShell after install)
winget install Python.Python.3.12

# Step 2: Open a NEW PowerShell window, then install pipx
pip install pipx
pipx ensurepath

# Step 3: Open ANOTHER new PowerShell window (required for PATH to take effect)
pipx install odoo-mcp-multi
odoo-mcp add-profile
odoo-mcp run
```

> **Windows notes:**
>
> - **Two terminal restarts required**: `winget install` and `pipx ensurepath` both modify
>   `PATH`. Each change only takes effect in a new terminal session.
> - **Credential file permissions**: on Linux/macOS, credentials are stored with `600`
>   (owner-read-only) Unix permissions. On Windows, `os.chmod` is silently ignored —
>   the file `%USERPROFILE%\.config\odoo-mcp\profiles.json` is created correctly but
>   without restricted permissions. Ensure your user account is the only account with
>   access to your machine.
> - **Python from python.org**: also works, but during installation you **must** check
>   *"Add Python to PATH"* (unchecked by default). Without it, `pip` won't be found.
> - **Microsoft Store Python**: avoid it — it runs in an app sandbox that can cause
>   issues with `pipx ensurepath` and file system access.

### Alternative: direct `pip install` (developer / existing venv)

```bash
pip install odoo-mcp-multi
odoo-mcp add-profile
odoo-mcp run
```

### Uninstall

All platforms (pipx recommended install):

```bash
pipx uninstall odoo-mcp-multi
```

> Credentials are **not** removed automatically. Delete the profile file manually if needed:
>
> - **macOS / Linux**: `~/.config/odoo-mcp/profiles.json`
> - **Windows**: `%USERPROFILE%\.config\odoo-mcp\profiles.json`

If you used `pip install` directly instead:

```bash
pip uninstall odoo-mcp-multi
```

## Profile Management

Profiles define how `odoo-mcp` connects to each Odoo instance. Each profile
stores a URL, database name, and authentication credentials (user/password for
Odoo < 19, or an API key for Odoo 19+).

```bash
# Interactive wizard (prompts for all fields)
odoo-mcp add-profile

# Non-interactive — Odoo < 19 (XML-RPC / JSON-RPC, user + password)
odoo-mcp add-profile --name prod --url https://odoo.example.com \
  --database mydb --user admin --password secret

# Non-interactive — Odoo 19+ (JSON/2 REST, API key)
odoo-mcp add-profile --name prod19 --url https://odoo19.example.com \
  --database mydb --api-key YOUR_API_KEY --protocol json2s
```

| Command | Description |
|---------|-------------|
| `odoo-mcp add-profile` | Register a new Odoo instance |
| `odoo-mcp list-profiles` | Show all configured profiles |
| `odoo-mcp edit-profile NAME` | Modify an existing profile |
| `odoo-mcp remove-profile NAME` | Delete a profile |
| `odoo-mcp set-default NAME` | Set the default profile |
| `odoo-mcp test -p NAME` | Test live connection |
| `odoo-mcp run` | Start the MCP server process |

## CLI Operations

All data commands support `--profile / -p` and output JSON for composability.

| Command | Description |
|---------|-------------|
| `odoo-mcp search-read -m MODEL` | Search and read records (`--domain`, `--fields`, `--limit`, `--offset`, `--order`, `--format`) |
| `odoo-mcp search-count -m MODEL` | Count records matching a domain without fetching data |
| `odoo-mcp write -m MODEL -i IDS -v VALUES` | Update existing records |
| `odoo-mcp unlink -m MODEL -i IDS` | Delete records |
| `odoo-mcp create -m MODEL -v VALUES` | Create a new record |
| `odoo-mcp export-records -m MODEL` | Export via native `export_data` (`--fields`, `--domain`) |
| `odoo-mcp import-records -m MODEL -f FIELDS -r ROWS` | Import via native `load` |
| `odoo-mcp execute-kw -m MODEL --method METHOD` | Execute any model method (`--args`, `--kwargs`) |
| `odoo-mcp get-version` | Retrieve server version info |
| `odoo-mcp list-models` | List available models (`--search` to filter) |
| `odoo-mcp list-fields -m MODEL` | List all fields of a model |

## MCP Client Configuration

The server handles multiple Odoo instances simultaneously. You only need to
declare one server definition in your AI client. To force a single default
profile, use `["run", "-p", "prod"]`.

```json
{
  "mcpServers": {
    "odoo": {
      "command": "odoo-mcp",
      "args": ["run"]
    }
  }
}
```

Add the block above to your client's MCP config file. Paths vary by tool and OS:

| Client | macOS | Linux | Windows |
|--------|-------|-------|---------|
| **Antigravity** | `~/.gemini/antigravity/mcp_config.json` | same | `%USERPROFILE%\.gemini\antigravity\mcp_config.json` |
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Cursor** | `.cursor/mcp.json` *(project root)* | same | same |
| **VS Code** | `.vscode/mcp.json` *(project root)* | same | same |

> **Note:** For Cursor and VS Code the config file is **workspace-scoped** — place it at the root of your project. For a user-level (global) config, check your client's own documentation.

## Available MCP Tools

All tools accept an optional `profile` string parameter to select the target
Odoo environment dynamically.

| Tool | Description |
|------|-------------|
| `list_available_profiles` | Discover configured environments |
| `search_read` | Query records with 5 output formats (json, compact, table, html, csv) |
| `search_count` | Count records without fetching data (~100 bytes response) |
| `write` | Update values on existing records |
| `unlink` | Delete records by ID |
| `create` | Create new records in a model |
| `export_records` | Native Odoo `export_data` returning dicts with External IDs |
| `import_records` | Native Odoo `load` bulk processor (upsert by External ID) |
| `execute_kw` | Execute arbitrary backend methods (`action_confirm`, `send`, etc.) |
| `list_models` | Discover available models (`search` filter) |
| `list_fields` | Inspect model schema (field names, types, metadata) |
| `get_version` | Retrieve server version and protocol info |

## Usage Examples

> "List all contacts containing 'John' in their name"

```python
search_read(model="res.partner", domain="[('name', 'ilike', 'John')]", fields="name,email,phone")
```

> "Create a new contact named Alice with email `alice@example.com`"

```python
create(model="res.partner", values='{"name": "Alice", "email": "alice@example.com"}')
```

> "Delete archived partners"

```python
unlink(model="res.partner", ids="[10, 11, 12]")
```

> "Confirm the sales order with ID 42"

```python
execute_kw(model="sale.order", method="action_confirm", args="[[42]]")
```

> "What fields does the invoice model have?"

```python
list_fields(model="account.move")
```

> "Export the name and external ID of all active partners"

```python
export_records(model="res.partner", domain="[('active', '=', True)]", fields="id,name")
```

> "Update the phone number of the partner with external ID 'base.res_partner_1' and create a new partner"

```python
import_records(model="res.partner", fields="id,name,phone", rows='[{"id": "base.res_partner_1", "name": "Existing Partner", "phone": "12345"}, {"name": "New Partner", "phone": "67890"}]')
```

## Security and Development

- Credentials are written to `~/.config/odoo-mcp/profiles.json` with `600` Unix permissions (owner-read-only). Passwords and API keys use Pydantic `SecretStr` to prevent accidental logging.
- Development mode: `pip install -e ".[dev]"`. Code quality is enforced by `ruff` (line length 119, mccabe complexity ≤ 15).
- Tests: `pytest` with `--cov` (290+ tests, 86%+ coverage).

---

<p align="center">
  <a href="https://vauxoo.com">
    <img src="https://git.vauxoo.com/nhomar/mcp.odoo/-/raw/main/docs/vauxoo.png"
         alt="Vauxoo" height="24" style="vertical-align:middle">
  </a>
  &nbsp;
  Maintained by <a href="https://nhomar.com"><strong>Nhomar Hernández</strong></a>
  at <a href="https://vauxoo.com"><strong>Vauxoo</strong></a> — Odoo Gold Partner.
  &nbsp;·&nbsp;
  <a href="https://git.vauxoo.com/nhomar/mcp.odoo/-/issues">Report an Issue</a>
</p>

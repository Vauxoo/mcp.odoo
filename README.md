# odoo-mcp-multi

[![PyPI version](https://img.shields.io/pypi/v/odoo-mcp-multi.svg)](https://pypi.org/project/odoo-mcp-multi/)
[![Python](https://img.shields.io/pypi/pyversions/odoo-mcp-multi.svg)](https://pypi.org/project/odoo-mcp-multi/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![pipeline status](https://git.vauxoo.com/nhomar/mcp.odoo/badges/main/pipeline.svg)](https://git.vauxoo.com/nhomar/mcp.odoo/-/pipelines)
[![coverage](https://git.vauxoo.com/nhomar/mcp.odoo/badges/main/coverage.svg)](https://git.vauxoo.com/nhomar/mcp.odoo/-/commits/main)

The **most tested, documented, and production-ready** MCP server for Odoo.
Connects any MCP client (Antigravity, Claude Desktop, Cursor, VS Code) to
**multiple Odoo instances simultaneously** — automatic protocol detection
(JSON-RPC 8.0+, JSON2 19.0+, XML-RPC legacy), secure credential storage
(Unix 600 permissions), 60+ tests, and full CLI parity for every MCP tool.

## 🌟 Features

- **Multi-profile management**: Store credentials for multiple environments (`prod`, `staging`, `dev`).
- **Secure by default**: Credentials safely stored in `~/.config/odoo-mcp/` (`600` permissions).
- **Multi-protocol Support**: JSON-RPC (8.0+), JSON2 (19.0+), XML-RPC (legacy) natively auto-detected.
- **10 Native MCP tools**: `search_read`, `write`, `create`, `export_records`, `import_records`, `execute_kw`, `list_models`, `list_fields`, `list_available_profiles`, `get_version`.
- **Full CLI parity**: Every MCP tool is also available as a CLI command — same logic, no duplication (DRY).
- **Integrated CLI**: Profile management, connection testing, and all Odoo data operations from your terminal.

## 📋 1-Minute Setup (Copy-Paste Prompt)

Paste this into your AI client (Antigravity, Claude, Cursor) to get started instantly:

> **Install & configure the Odoo MCP server.** Run these steps:
>
> 1. Install (recommended — isolated, no venv needed):
>    - macOS: `brew install pipx && pipx install odoo-mcp-multi`
>    - Linux: `pip install pipx && pipx install odoo-mcp-multi`
>    - Windows: `winget install Python.Python.3.12` → new terminal → `pip install pipx && pipx ensurepath` → new terminal → `pipx install odoo-mcp-multi`
>    - Developer alternative: `pip install odoo-mcp-multi`
> 2. Add a profile: `odoo-mcp add-profile` (enter your Odoo URL, database, user, and API key)
> 3. Test connection: `odoo-mcp test`
> 4. Add this block to your AI client's MCP config file (locate the right path for your tool and OS in the [⚙️ MCP Client Configuration](#️-mcp-client-configuration) section below):
>
>    ```json
>    {
>      "mcpServers": {
>        "odoo": {
>          "command": "odoo-mcp",
>          "args": ["run"]
>        }
>      }
>    }
>    ```
>
> 5. Restart your AI client. You now have access to 10 Odoo tools: `search_read`, `write`, `create`, `export_records`, `import_records`, `execute_kw`, `list_models`, `list_fields`, `list_available_profiles`, `get_version`.

## 🚀 Installation & Quick Start

`pipx` is the recommended installer for all platforms — it automatically creates
an isolated virtual environment per tool and exposes `odoo-mcp` globally,
with no virtualenv management required.

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

> **⚠️ Windows side corners:**
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

### 🗑️ Uninstall

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

## 💻 CLI Operations

All operations are available directly from your terminal. Use `odoo-mcp [COMMAND] --help` for specific flags.

### Profile Management

- `odoo-mcp add-profile`: Interactive wizard to register a new instance.
- `odoo-mcp list-profiles`: Displays all configured profiles.
- `odoo-mcp edit-profile NAME`: Modify credentials, URLs, or database of an existing profile.
- `odoo-mcp remove-profile NAME`: Deletes a profile.
- `odoo-mcp set-default NAME`: Sets the default profile.
- `odoo-mcp test -p NAME`: Tests live connection to confirm credentials are working.
- `odoo-mcp run`: **Starts the MCP server process.**

### Odoo Data Operations

All data commands support `--profile / -p` and output JSON for composability.

- `odoo-mcp search-read -m MODEL`: Search and read records (`--domain`, `--fields`, `--limit`, `--offset`, `--order`).
- `odoo-mcp write -m MODEL -i IDS -v VALUES`: Update existing records.
- `odoo-mcp create -m MODEL -v VALUES`: Create a new record.
- `odoo-mcp export-records -m MODEL`: Export via native `export_data` (`--fields`, `--domain`).
- `odoo-mcp import-records -m MODEL -f FIELDS -r ROWS`: Import via native `load`.
- `odoo-mcp execute-kw -m MODEL --method METHOD`: Execute any model method (`--args`, `--kwargs`).
- `odoo-mcp get-version`: Retrieve server version info.
- `odoo-mcp list-models`: List available models (`--search` to filter).
- `odoo-mcp list-fields -m MODEL`: List all fields of a model.

## ⚙️ MCP Client Configuration

The server gracefully handles multiple Odoo instances simultaneously. You only need to declare one server definition in your AI client. You can optionally force a single fallback using `["run", "-p", "prod"]`.

**Global Configuration Block:**

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

## 🛠 Available MCP Tools

*All tools accept an optional `profile` string parameter to dynamically select the target Odoo environment.*

- `list_available_profiles`: Discovers the local environments available.
- `search_read`: Queries records from any model based on domains.
- `write`: Updates values on existing records.
- `create`: Instantiates new records in a model.
- `export_records`: Native Odoo `export_data` returning a clean array of dicts (Useful for relational lookup and retrieving XML External IDs `id`).
- `import_records`: Native Odoo `load` bulk processor. Updates existing records if External IDs are provided, or creates new ones.
- `execute_kw`: Executes arbitrary backend methods (`action_confirm`, `send`, etc).
- `list_models` / `list_fields`: Discovers the system's schema architecture.
- `get_version`: Retrieves server version mapping.

## 💡 Usage Examples in Claude

> "List all contacts containing 'John' in their name"

```python
search_read(model="res.partner", domain="[('name', 'ilike', 'John')]", fields="name,email,phone")
```

> "Create a new contact named Alice with email <alice@example.com>"

```python
create(model="res.partner", values='{"name": "Alice", "email": "alice@example.com"}')
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

## 🛡 Security & Development

- Credentials securely written to `~/.config/odoo-mcp/profiles.json` without raw logging.
- Development mode requires `pip install -e ".[dev]"`. Code standard is heavily enforced by `ruff`.

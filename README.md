# odoo-mcp-multi

MCP Server for connecting MCP clients (Antigravity, Claude Desktop, Cursor, VS Code) to multiple Odoo instances.

## 🌟 Features

- **Multi-profile management**: Store credentials for multiple environments (`prod`, `staging`, `dev`).
- **Secure by default**: Credentials safely stored in `~/.config/odoo-mcp/` (`600` permissions).
- **Multi-protocol Support**: JSON-RPC (8.0+), JSON2 (19.0+), XML-RPC (legacy) natively auto-detected.
- **10 Native MCP tools**: `search_read`, `write`, `create`, `export_records`, `import_records`, `execute_kw`, `list_models`, `list_fields`, `list_available_profiles`, `get_version`.
- **Full CLI parity**: Every MCP tool is also available as a CLI command — same logic, no duplication (DRY).
- **Integrated CLI**: Profile management, connection testing, and all Odoo data operations from your terminal.

## 🚀 Installation & Quick Start

```bash
# Install package
pip install odoo-mcp-multi

# 1. Add your Odoo instance credentials
odoo-mcp add-profile

# 2. Start MCP server (Optional: lock to a specific profile with -p)
odoo-mcp run
```

## 📋 1-Minute Setup (Copy-Paste Prompt)

Paste this into your AI client (Antigravity, Claude, Cursor) to get started instantly:

> **Install & configure the Odoo MCP server.** Run these steps:
>
> 1. Install: `pip install odoo-mcp-multi`
> 2. Add a profile: `odoo-mcp add-profile` (enter your Odoo URL, database, user, and API key)
> 3. Test connection: `odoo-mcp test`
> 4. Add this to your MCP client config (`~/.gemini/antigravity/mcp_config.json` for Antigravity, `~/Library/Application Support/Claude/claude_desktop_config.json` for Claude Desktop, `.cursor/mcp.json` for Cursor):
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
> 5. Restart your AI client. You now have access to 10 Odoo tools: `search_read`, `write`, `create`, `export_records`, `import_records`, `execute_kw`, `list_models`, `list_fields`, `list_available_profiles`, `get_version`.

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

Add the block above to your respective client configuration file:
- **Antigravity**: `~/.gemini/antigravity/mcp_config.json`
- **Claude Desktop**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Cursor**: `.cursor/mcp.json`
- **VS Code**: `.vscode/mcp.json`

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

> "Create a new contact named Alice with email alice@example.com"
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

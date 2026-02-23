# odoo-mcp-multi

MCP Server for connecting MCP clients (Antigravity, Claude Desktop, Cursor, VS Code) to multiple Odoo instances.

## Features

- **Multi-profile management**: Store credentials for multiple environments (prod, staging, dev)
- **Secure storage**: Credentials stored in `~/.config/odoo-mcp/` with 600 permissions
- **Multi-protocol**: JSON-RPC (8.0+), JSON2 (19.0+), XML-RPC (legacy) with automatic detection
- **7 MCP tools**: `search_read`, `write`, `create`, `execute_kw`, `list_models`, `list_fields`, `get_version`
- **Full CLI**: Profile and MCP server management

## Installation

```bash
# Using pip
pip install .

# Using uv
uv pip install .

# Development mode
pip install -e .
```

After installation, the `odoo-mcp` command will be available in your PATH.

---

## Quick Start

```bash
# 1. Add a profile
odoo-mcp add-profile

# 2. Verify connection
odoo-mcp test -p prod

# 3. Start MCP server
odoo-mcp run -p prod
```

---

## CLI Commands

### `odoo-mcp add-profile`

Interactive wizard to add an Odoo instance's credentials.

```bash
odoo-mcp add-profile
```

**Options:**
| Option | Description |
|--------|-------------|
| `--name TEXT` | Profile identifier (e.g., `prod`, `staging`) |
| `--url TEXT` | Instance URL (e.g., `https://odoo.example.com`) |
| `--database TEXT` | Database name |
| `--user TEXT` | Odoo user |
| `--password TEXT` | Password (hidden on typing) |
| `--default` | Set as default profile |
| `--test / --no-test` | Test connection before saving (default: `--test`) |

**Non-interactive example:**
```bash
odoo-mcp add-profile \
  --name prod \
  --url https://erp.mycompany.com \
  --database production \
  --user admin \
  --password secret \
  --default
```

---

### `odoo-mcp list-profiles`

Displays all configured profiles.

```bash
odoo-mcp list-profiles
```

**Options:**
| Option | Description |
|--------|-------------|
| `--json` | JSON output format |

**Sample output:**
```text
Configured Profiles:
------------------------------------------------------------
  prod (default)
    URL:      https://erp.mycompany.com
    Database: production
    User:     admin

  staging
    URL:      https://staging.mycompany.com
    Database: staging_db
    User:     admin
```

---

### `odoo-mcp edit-profile`

Modifies an existing profile. Only the specified fields will be updated.

```bash
odoo-mcp edit-profile NAME [OPTIONS]
```

**Arguments:**
| Argument | Description |
|-----------|-------------|
| `NAME` | Name of the profile to edit (required) |

**Options:**
| Option | Description |
|--------|-------------|
| `--url TEXT` | New URL |
| `--database TEXT` | New database name |
| `--user TEXT` | New username |
| `--password` | Interactively prompt for new password |
| `--test` | Test connection after editing |

**Examples:**
```bash
# Change only the URL
odoo-mcp edit-profile prod --url https://new-url.com

# Change username and password
odoo-mcp edit-profile staging --user new_admin --password

# Change database and test connection
odoo-mcp edit-profile dev --database new_db --test
```

---

### `odoo-mcp remove-profile`

Removes a profile by name.

```bash
odoo-mcp remove-profile NAME
```

**Options:**
| Option | Description |
|--------|-------------|
| `-f, --force` | Skip confirmation |

**Example:**
```bash
odoo-mcp remove-profile staging -f
```

---

### `odoo-mcp set-default`

Sets the default profile.

```bash
odoo-mcp set-default NAME
```

**Example:**
```bash
odoo-mcp set-default prod
```

---

### `odoo-mcp test`

Tests the connection to an Odoo instance.

```bash
odoo-mcp test [-p PROFILE]
```

**Options:**
| Option | Description |
|--------|-------------|
| `-p, --profile TEXT` | Profile to use (default: default profile) |

**Example:**
```bash
odoo-mcp test -p prod
# ✓ Connection successful! Authenticated as UID 2
#   Server version: 16.0
#   Protocol: auto
```

---

### `odoo-mcp run`

Starts the MCP server.

```bash
odoo-mcp run [-p PROFILE]
```

**Options:**
| Option | Description |
|--------|-------------|
| `-p, --profile TEXT` | Profile to use (default: default profile) |

**Example:**
```bash
odoo-mcp run -p prod
# Starting MCP server with profile 'prod'...
#   URL: https://erp.mycompany.com
#   Database: production
#   User: admin
```

---

## MCP Clients Configuration

### Multi-Profile Configuration

The MCP server handles multi-instance connections **dynamically**. You only need to declare a single server in your AI editor. When the AI uses a tool, it can pass a `profile` argument to target a specific instance.

#### Recommended Setup

Declare a single server without forcing a profile parameter on startup:

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

Then you can tell the AI: *"In the 'prod' profile, look for the CRM leads"*.
The AI will use the `list_available_profiles` tool to see your configured profiles and pass `"profile": "prod"` automatically.

If the AI doesn't pass a profile, the server will fallback to the profile marked as default in your local configuration.

#### Forced Default Setup

If you want the fallback profile to be completely explicit regardless of local `odoo-mcp set-default`, use the `-p` argument:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "odoo-mcp",
      "args": ["run", "-p", "prod"]
    }
  }
}
```

---

### Antigravity

Edit `~/.gemini/antigravity/mcp_config.json`:

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

> **Note**: Restart Antigravity after modifying the configuration.

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

### Cursor

Edit `.cursor/mcp.json` in your project or globally:

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

### VS Code (with MCP extension)

Edit `.vscode/mcp.json` or the global configuration:

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

---

## Available MCP Tools

Once the server is running, these tools are available for Claude/Cursor. **All tools accept an optional `profile` parameter** to target a specific Odoo instance dynamically.

### `list_available_profiles`

Lists all locally configured Odoo profiles. The AI can use this to discover available environments before making requests.

*No parameters.*

---

### `search_read`

Searches and reads records from a model.

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name (e.g., `res.partner`) |
| `domain` | string | Search domain (e.g., `[('name', 'ilike', 'John')]`) |
| `fields` | string | Comma-separated fields (e.g., `name,email,phone`) |
| `limit` | int | Maximum records (default: 100) |
| `offset` | int | Records to skip (default: 0) |
| `order` | string | Sorting (e.g., `name asc, id desc`) |
| `profile` | string | *(Optional)* Target Odoo profile name |

---

### `write`

Updates existing records.

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name |
| `ids` | string | IDs as JSON or comma-separated (e.g., `[1,2,3]` or `1,2,3`) |
| `values` | string | Values as JSON (e.g., `{"name": "New Name"}`) |
| `profile` | string | *(Optional)* Target Odoo profile name |

---

### `create`

Creates a new record.

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name |
| `values` | string | Values as JSON (e.g., `{"name": "Alice", "email": "alice@example.com"}`) |
| `profile` | string | *(Optional)* Target Odoo profile name |

---

### `export_records`

Exports records from a model using native `export_data`. Returns a clean array of dictionaries, ideal for bulk operations.

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name |
| `domain` | string | Search domain (e.g., `[('name', 'ilike', 'John')]`) |
| `fields` | string | Comma-separated fields. Use `id` for External ID, and `rel/id` for relations (e.g., `id,name,country_id/id`) |
| `profile` | string | *(Optional)* Target Odoo profile name |

---

### `import_records`

Imports and updates records via native `load`. If the `id` field contains an External ID, the record is updated. Returns detailed line-by-line messages on format errors.

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name |
| `fields` | string | Comma-separated field names matching the keys (e.g., `id,name`) |
| `rows` | string | JSON array of dictionaries containing the data. |
| `profile` | string | *(Optional)* Target Odoo profile name |

---

### `execute_kw`

Executes any method of an Odoo model.

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name |
| `method` | string | Method name (e.g., `action_confirm`, `send`) |
| `args` | string | Positional arguments as JSON (e.g., `[[42]]`) |
| `kwargs` | string | Keyword arguments as JSON (e.g., `{"force_send": true}`) |
| `profile` | string | *(Optional)* Target Odoo profile name |

---

### `list_models`

Lists the models available in the instance.

| Parameter | Type | Description |
|-----------|------|-------------|
| `search` | string | Optional filter by model name |
| `profile` | string | *(Optional)* Target Odoo profile name |

---

### `list_fields`

Lists the fields of a model.

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name |
| `profile` | string | *(Optional)* Target Odoo profile name |

---

### `get_version`

Gets version information from the Odoo server.

| Parameter | Type | Description |
|-----------|------|-------------|
| `profile` | string | *(Optional)* Target Odoo profile name |

---

## Usage Examples in Claude

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

---

## Security

- Credentials are stored in `~/.config/odoo-mcp/profiles.json`
- File permissions are set to `600` (owner read/write only)
- Passwords are handled with `SecretStr` to prevent accidental logging

---

## Development

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Run linting
ruff check odoo_mcp_multi/

# Format code
ruff format odoo_mcp_multi/
```

---

## License

MIT

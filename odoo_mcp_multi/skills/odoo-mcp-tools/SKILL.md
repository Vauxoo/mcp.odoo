---
name: "odoo-mcp-tools"
description: "Use this skill to query, create, update, delete, export, or import records in any Odoo instance via MCP tools. Triggers on: 'search records', 'create record', 'update partner', 'delete record', 'unlink record', 'export data', 'import records', 'execute method', 'list models', 'list fields', 'get version', 'list profiles', 'odoo mcp tools'."
last_validated: 2026-05-09
---

# Odoo MCP Tools Reference

Complete reference for the 11 MCP tools provided by `odoo-mcp-multi`.
Use this skill when interacting with any Odoo instance via an MCP client
(Antigravity, Claude Desktop, Cursor, VS Code).

## Prerequisites

- `odoo-mcp-multi` installed (`pip install odoo-mcp-multi`)
- At least one Odoo profile configured (`odoo-mcp add-profile`)
- MCP server registered in the AI client config (see Client Configuration below)

## Steps

1. Call `list_available_profiles` to discover which Odoo environments are available.
2. Use the `profile` parameter in any tool call to target a specific environment.
3. If unsure of the model name, use `list_models` to search. If unsure of field names, use `list_fields`.

## Client Configuration

Register the server in your AI client's MCP config file:

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

Config file paths by client and OS:

| Client | macOS | Linux | Windows |
|--------|-------|-------|---------|
| **Antigravity** | `~/.gemini/antigravity/mcp_config.json` | same | `%USERPROFILE%\.gemini\antigravity\mcp_config.json` |
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Cursor** | `.cursor/mcp.json` *(project root)* | same | same |
| **VS Code** | `.vscode/mcp.json` *(project root)* | same | same |

> **Note:** Cursor and VS Code configs are workspace-scoped — place the file at the root of your project.
>
> **Tip:** After installing `odoo-mcp-multi`, run `odoo-mcp skills install <agent>` (e.g., `antigravity`, `claude`, `gemini`) to symlink these skills into your IDE's global skills directory.

---

## Tools Reference

### `list_available_profiles` — Discover Environments

Lists all configured Odoo profiles with name, URL, database, and default status.

```python
list_available_profiles()
```

---

### `search_read` — Query Records

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name (e.g., `res.partner`) |
| `domain` | string | `[]` | Search domain |
| `fields` | string | `""` | Comma-separated field names |
| `limit` | int | `100` | Max records to return |
| `offset` | int | `0` | Records to skip (pagination) |
| `order` | string | `""` | Sort order (e.g., `name asc`) |
| `profile` | string | *(default)* | Target profile name |

Returns a **pagination envelope**:

```json
{
  "records": [{"id": 1, "name": "Alice"}],
  "total": 1500,
  "limit": 100,
  "offset": 0,
  "has_more": true,
  "next_offset": 100
}
```

> **Important:** Always check `has_more` — if `true`, use `next_offset` to fetch the next page.

```python
search_read(model="res.partner", domain="[('is_company', '=', True)]", fields="name,email", limit=10, profile="prod")
```

#### Pagination pattern

Always check `has_more` — if `true`, call again with `next_offset`:

```python
# Page 1
result = search_read(model="res.partner", fields="name", limit=100, offset=0)
# result["has_more"] == true, result["next_offset"] == 100

# Page 2
result = search_read(model="res.partner", fields="name", limit=100, offset=100)
# Continue until has_more == false
```

---

### `write` — Update Records

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `ids` | string | *(required)* | Record IDs as JSON array or comma-separated |
| `values` | string | *(required)* | Field values as JSON object |
| `profile` | string | *(default)* | Target profile name |

```python
write(model="res.partner", ids="[1, 2]", values='{"phone": "+52 555 1234"}', profile="prod")
```

---

### `unlink` — Delete Records

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `ids` | string | *(required)* | Record IDs as JSON array or comma-separated |
| `profile` | string | *(default)* | Target profile name |

```python
unlink(model="res.partner", ids="[10, 11, 12]", profile="prod")
```

---

### `create` — Create Records

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `values` | string | *(required)* | Field values as JSON object |
| `profile` | string | *(default)* | Target profile name |

```python
create(model="res.partner", values='{"name": "Alice", "email": "alice@example.com"}', profile="prod")
```

---

### `export_records` — Native Export

Export via Odoo's `export_data`. Returns a **pagination envelope** with an array of
dicts — ideal for retrieving External IDs.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `domain` | string | `[]` | Search domain |
| `fields` | string | `id,name` | Comma-separated field names |
| `limit` | int | `500` | Max records to export |
| `offset` | int | `0` | Records to skip (pagination) |
| `profile` | string | *(default)* | Target profile name |

```python
export_records(model="res.partner", domain="[('active', '=', True)]", fields="id,name,country_id/id")
```

> **Tip:** Use `field_id/id` syntax to export External IDs of relational fields.
> Check `has_more` in the response to know if more pages exist.

---

### `import_records` — Native Import (Bulk)

Import via Odoo's `load`. Updates records with matching External IDs; creates new ones otherwise.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `fields` | string | *(required)* | Comma-separated field names |
| `rows` | string | *(required)* | JSON array of dicts with data |
| `profile` | string | *(default)* | Target profile name |

```python
import_records(model="res.partner", fields="id,name,phone", rows='[{"id": "base.res_partner_1", "name": "Updated", "phone": "12345"}, {"name": "New Partner", "phone": "67890"}]')
```

---

### `execute_kw` — Execute Any Method

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `method` | string | *(required)* | Method to execute |
| `args` | string | `[]` | Positional arguments as JSON array |
| `kwargs` | string | `{}` | Keyword arguments as JSON object |
| `profile` | string | *(default)* | Target profile name |

```python
execute_kw(model="sale.order", method="action_confirm", args="[[42]]")
```

---

### `list_models` — Discover Models

```python
list_models(search="partner", profile="prod")
```

---

### `list_fields` — Inspect Model Schema

```python
list_fields(model="account.move", profile="prod")
```

---

### `get_version` — Server Version

```python
get_version(profile="prod")
```

---

## Domain Syntax Quick Reference

| Natural Language | Odoo Domain |
|------------------|-------------|
| name contains "Juan" | `[('name', 'ilike', 'Juan')]` |
| state is "sale" | `[('state', '=', 'sale')]` |
| amount > 1000 | `[('amount_total', '>', 1000)]` |
| date after 2024-01-01 | `[('create_date', '>=', '2024-01-01')]` |
| country is Mexico or USA | `['\|', ('country_id.code', '=', 'MX'), ('country_id.code', '=', 'US')]` |

| Operator | Meaning |
|----------|---------|
| `=` | Equal |
| `!=` | Not equal |
| `ilike` | Case-insensitive contains |
| `>`, `<`, `>=`, `<=` | Comparison |
| `in` | Value in list |
| `not in` | Value not in list |

---

## Usage Examples

### Example 1: Search for contacts by name

**User:** "Find all contacts with 'John' in their name"

**Action:**

```python
search_read(model="res.partner", domain="[('name', 'ilike', 'John')]", fields="name,email,phone")
```

### Example 2: Export and re-import records between environments

**User:** "Export all active products from staging and import them to prod"

**Action:**

```python
# Step 1: Export from staging
export_records(model="product.template", domain="[('active', '=', True)]", fields="id,name,list_price", profile="staging")

# Step 2: Import to prod (use the exported rows as input)
import_records(model="product.template", fields="id,name,list_price", rows="[...]", profile="prod")
```

---

## Error Handling

All tools return JSON. On error, the response contains an `error` key:

```json
{"error": "Profile 'staging' not found."}
```

| Error | Cause | Fix |
|-------|-------|-----|
| Profile not found | Invalid profile name | Run `list_available_profiles` |
| Connection refused | Odoo server down or wrong URL | Check profile URL and port |
| Model not found | Typo in model name | Use `list_models` to discover |
| Access denied | Wrong credentials or permissions | Verify profile credentials |

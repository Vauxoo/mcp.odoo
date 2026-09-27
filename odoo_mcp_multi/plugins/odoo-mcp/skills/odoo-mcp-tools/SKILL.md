---
name: "odoo-mcp-tools"
description: "Use this skill when you need to query, create, update, delete, export, or import records in any Odoo instance via MCP tools. Triggers on: 'search records', 'create record', 'update partner', 'delete record', 'unlink record', 'export data', 'import records', 'execute method', 'list models', 'list fields', 'get version', 'list profiles', 'odoo mcp tools'."
last_validated: 2026-09-25
---

# Odoo MCP Tools Reference

Complete reference for the 13 MCP tools provided by `odoo-mcp-multi`.
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
4. Send calls that depend on each other one at a time, never in the same parallel batch (see Concurrent Tool Calls).

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

### Shared HTTP server (many sessions, one process)

With the config above each client session starts its own server. When many
sessions stay open at once, start one server with
`odoo-mcp serve --auth local --port 5010` (see the `odoo-mcp-cli` skill for
its flags, why it only binds loopback and where its token lives) and point
every client at it:

```json
{
  "mcpServers": {
    "odoo": {
      "type": "http",
      "url": "http://127.0.0.1:5010/mcp",
      "headers": {"Authorization": "Bearer <contents of ~/.config/odoo-mcp/local-token>"}
    }
  }
}
```

Keep the server name `odoo` so tool names and permissions stay the same. The
Claude Code plugin of this package declares its own stdio `odoo` server, so a
session with the plugin enabled still starts one process of its own.

## Concurrent Tool Calls

The server runs each tool call in a worker thread, so calls from different
sessions, and calls an agent sends in parallel, really execute at the same
time. Two consequences:

- **Calls sent in the same parallel batch can run in any order.** Never batch
  calls that depend on each other: `create` then `write` on the new id,
  `search_count` before `unlink`, a read that must see a write. Send them one
  after another and wait for each result.
- Up to 32 calls run at once in `serve` (`--max-concurrency`), 40 in `run`;
  further calls wait for a free worker without blocking the server.

## Sandbox Execution Rail

If executing `odoo-mcp` CLI commands inside a sandboxed AI agent environment results in:

- `Fatal Python error: init_import_site` OR `PermissionError: .../pyvenv.cfg`

Refer to `AGENT.md` / `CLAUDE.md` at repository root for least-privilege target path permissions (`~/.local/pipx/venvs/odoo-mcp-multi/` or `~/.local/share/uv/tools/odoo-mcp-multi/`) and zero-retry resolution directives.

---

## Tools Reference

### `list_available_profiles` — Discover Environments

Lists all configured Odoo profiles with name, URL, database, and default status.

```python
list_available_profiles()
# -> {"count": 25, "profiles": [{"name": "prod", "url": "...", "database": "...", "is_default": true}, ...]}
```

Report the number of profiles from `count`; do not count the list yourself.

---

### `search_read` — Query Records

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name (e.g., `res.partner`) |
| `domain` | string | `[]` | Search domain |
| `fields` | string | `""` | Comma-separated field names (explicit fields recommended) |
| `limit` | int | `25` | Max records to return (default: 25) |
| `offset` | int | `0` | Records to skip (pagination) |
| `order` | string | `""` | Sort order (e.g., `name asc`) |
| `format` | string | `json` | Response format (see below) |
| `profile` | string | *(default)* | Target profile name |

> **Token Efficiency Tip:** Results remain in context for the entire session. Always pass explicit `fields` (omitting `fields` returns all fields and adds an efficiency hint). Prefer `format='compact'` or `'csv'` for large reads to cut token usage by ~60%.

#### Response formats

Choose the format based on what you need to do with the data:

| Format | Data key | Token cost | Data loss | Best for |
|--------|----------|-----------|-----------|----------|
| `json` | `records` | High (baseline) | None | Parsing/processing values programmatically |
| `compact` | `headers` + `rows` | ~40% of json | None | Exploring large datasets efficiently |
| `table` | `data` (Markdown) | ~40% of json | Truncates >50 chars | Showing summaries to the user in chat |
| `html` | `data` (HTML) | ~50% of json | None | Pasting into Odoo chatter/Knowledge/reports |
| `csv` | `data` (CSV) | ~30% of json | None | Spreadsheet export or feeding back to `import_records` |

All formats include the same **pagination envelope** (`total`, `limit`, `offset`, `has_more`, `next_offset`, `format`).

**Default (json):**

```json
{
  "records": [{"id": 1, "name": "Alice"}],
  "total": 1500,
  "limit": 25,
  "offset": 0,
  "has_more": true,
  "next_offset": 25,
  "format": "json"
}
```

**compact:**

```json
{
  "headers": ["id", "name"],
  "rows": [[1, "Alice"], [2, "Bob"]],
  "total": 1500,
  "has_more": true,
  "format": "compact"
}
```

> **Important:** Always check `has_more` — if `true`, use `next_offset` to fetch the next page.

```python
# Default JSON format
search_read(model="res.partner", domain="[('is_company', '=', True)]", fields="name,email", limit=10, profile="prod")

# Compact format for large datasets
search_read(model="res.partner", fields="name,email,phone", limit=500, format="compact")

# Markdown table for user-facing summaries
search_read(model="sale.order", fields="name,partner_id,amount_total,state", format="table")

# HTML for pasting into Odoo
search_read(model="res.partner", fields="name,email", format="html")

# CSV for spreadsheet export
search_read(model="res.partner", fields="name,email,phone", format="csv")
```

#### Pagination pattern

Always check `has_more` — if `true`, call again with `next_offset`:

```python
# Page 1
result = search_read(model="res.partner", fields="name", limit=25, offset=0)
# result["has_more"] == true, result["next_offset"] == 25

# Page 2
result = search_read(model="res.partner", fields="name", limit=25, offset=25)
# Continue until has_more == false
```

---

### `search_count` — Count Records

Token-efficient sizing probe (~100 bytes): call it before a wide
`search_read` to decide on `limit`/pagination instead of reading blind.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `domain` | string | `[]` | Search domain |
| `profile` | string | *(default)* | Target profile name |

```python
search_count(model="account.move", domain="[('state', '=', 'posted')]")
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
| `format` | string | `json` | Response format: `json`, `compact`, `table`, `html`, `csv` |
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
import_records(
    model="res.partner",
    fields="id,name,phone",
    rows='[{"id": "base.res_partner_1", "name": "Updated", "phone": "12345"}, {"name": "New Partner", "phone": "67890"}]',
)
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

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search` | string | `""` | Filter models by name or technical name |
| `format` | string | `json` | Response format: `json`, `compact`, `table`, `html`, `csv` |
| `profile` | string | *(default)* | Target profile name |

```python
list_models(search="partner", profile="prod")
```

---

### `list_fields` — Inspect Model Schema

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name to inspect |
| `format` | string | `json` | Response format: `json`, `compact`, `table`, `html`, `csv` |
| `profile` | string | *(default)* | Target profile name |

```python
list_fields(model="account.move", profile="prod")
```

---

### `get_version` — Server Version

```python
get_version(profile="prod")
```

---

### `get_financial_report` — Financial Reports

Calculate and format Odoo financial reports (Balance Sheet, P&L, Trial
Balance, ledgers) for Odoo 17.0, 18.0 and 19.0+. For the full report
catalog, date filters, and formatting guidance use the dedicated
`odoo-financial-reports` skill.

```python
get_financial_report(report_id_or_name="Balance Sheet", date_filter="this_year", format="table")
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
export_records(
    model="product.template", domain="[('active', '=', True)]", fields="id,name,list_price", profile="staging"
)

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

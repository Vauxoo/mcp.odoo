# MCP Tools Reference

This reference documents each MCP tool provided by `odoo-mcp-multi`. Use this as a skill guide when interacting with Odoo instances via any MCP client (Antigravity, Claude Desktop, Cursor, VS Code).

---

## Pre-flight: Discover Available Profiles

Always start by discovering which Odoo environments are configured:

```
Tool: list_available_profiles
```

This returns all profiles with their name, URL, database, and default status. Use the profile `name` in subsequent tool calls.

---

## Tools Reference

### `search_read` — Query Records

Search and read records from any Odoo model.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name (e.g., `res.partner`) |
| `domain` | string | `[]` | Search domain (e.g., `[('name', 'ilike', 'John')]`) |
| `fields` | string | `""` | Comma-separated field names |
| `limit` | int | `100` | Maximum records to return |
| `offset` | int | `0` | Records to skip |
| `order` | string | `""` | Sort order (e.g., `name asc`) |
| `profile` | string | *(default)* | Target profile name |

```python
search_read(model="res.partner", domain="[('is_company', '=', True)]", fields="name,email", limit=10, profile="prod")
```

---

### `write` — Update Records

Update existing records in Odoo.

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

### `create` — Create Records

Create a new record in Odoo.

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

Export records using Odoo's native `export_data`. Returns an array of dicts — ideal for retrieving External IDs (`id` field).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `domain` | string | `[]` | Search domain |
| `fields` | string | `id,name` | Comma-separated field names |
| `profile` | string | *(default)* | Target profile name |

```python
export_records(model="res.partner", domain="[('active', '=', True)]", fields="id,name,country_id/id")
```

> **Tip:** Use `field_id/id` syntax to export External IDs of relational fields — essential for stable `import_records` operations.

---

### `import_records` — Native Import (Bulk)

Import records using Odoo's native `load`. If an `id` column contains External IDs, existing records are **updated**; otherwise, new records are **created**.

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

Execute arbitrary backend methods on any model.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `method` | string | *(required)* | Method to execute |
| `args` | string | `[]` | Positional arguments as JSON array |
| `kwargs` | string | `{}` | Keyword arguments as JSON object |
| `profile` | string | *(default)* | Target profile name |

```python
# Confirm a sale order
execute_kw(model="sale.order", method="action_confirm", args="[[42]]")

# Get default values
execute_kw(model="res.partner", method="default_get", args='[["name", "email"]]')
```

---

### `list_models` — Discover Models

List available models in the Odoo instance.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search` | string | `""` | Filter by model name or technical name |
| `profile` | string | *(default)* | Target profile name |

```python
list_models(search="partner", profile="prod")
```

---

### `list_fields` — Inspect Model Schema

List all fields of a specific model.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `profile` | string | *(default)* | Target profile name |

```python
list_fields(model="account.move", profile="prod")
```

---

### `get_version` — Server Version

Retrieve version info from the Odoo server.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `profile` | string | *(default)* | Target profile name |

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
| country is Mexico or USA | `['|', ('country_id.code', '=', 'MX'), ('country_id.code', '=', 'US')]` |

### Operators

| Operator | Meaning |
|----------|---------|
| `=` | Equal |
| `!=` | Not equal |
| `ilike` | Case-insensitive contains |
| `>`, `<`, `>=`, `<=` | Comparison |
| `in` | Value in list |
| `not in` | Value not in list |
| `like` | Case-sensitive contains |
| `child_of` | Hierarchical (parent chain) |

---

## Error Handling

All tools return JSON. On success, you get the data directly. On error, you get a JSON object with an `error` key:

```json
{"error": "Profile 'staging' not found."}
```

Common errors:

| Error | Cause | Fix |
|-------|-------|-----|
| Profile not found | Invalid profile name | Run `list_available_profiles` |
| Connection refused | Odoo server down or wrong URL | Check profile URL and port |
| Model not found | Typo in model name | Use `list_models` to discover |
| Access denied | Wrong credentials or permissions | Verify profile credentials |

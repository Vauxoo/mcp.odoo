# MCP Tools Reference

Complete reference for the 12 MCP tools provided by `odoo-mcp-multi`.

!!! tip "When to use this"
    Use the MCP tools when interacting with Odoo via an AI client
    (Antigravity, Claude Desktop, Cursor, VS Code). For CLI access,
    see the [CLI Reference](cli.md).

## Pagination Envelope

`search_read` and `export_records` return a structured envelope instead
of a plain list. This lets agents handle large datasets without losing context:

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

!!! important
    Always check `has_more`. If `true`, use `next_offset` to fetch the next page.

---

## `list_available_profiles`

Lists all configured Odoo profiles with name, URL, database, and default status.

```python
list_available_profiles()
```

---

## `search_read`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name (e.g., `res.partner`) |
| `domain` | string | `[]` | Search domain |
| `fields` | string | `""` | Comma-separated field names |
| `limit` | int | `100` | Max records to return |
| `offset` | int | `0` | Records to skip (pagination) |
| `order` | string | `""` | Sort order |
| `format` | string | `json` | Output format: `json`, `compact`, `table`, `html`, `csv` |
| `profile` | string | *(default)* | Target profile name |

```python
search_read(
    model="res.partner",
    domain="[('is_company', '=', True)]",
    fields="name,email",
    limit=10,
    format="table",
    profile="prod"
)
```

---

## `search_count`

Count records matching a domain without fetching data. Returns ~100 bytes
instead of potentially hundreds of KB.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `domain` | string | `[]` | Search domain |
| `profile` | string | *(default)* | Target profile |

```python
search_count(model="account.move", domain="[('state', '=', 'posted')]")
```

---

## `write`

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name |
| `ids` | string | Record IDs as JSON array or comma-separated |
| `values` | string | Field values as JSON object |
| `profile` | string | Target profile |

```python
write(model="res.partner", ids="[1, 2]", values='{"phone": "+52 555 1234"}')
```

---

## `create`

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name |
| `values` | string | Field values as JSON object |
| `profile` | string | Target profile |

```python
create(model="res.partner", values='{"name": "Alice", "email": "alice@example.com"}')
```

---

## `export_records`

Returns a **pagination envelope** (same structure as `search_read`).
Use `field/id` syntax to export External IDs of relational fields.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `domain` | string | `[]` | Search domain |
| `fields` | string | `id,name` | Comma-separated fields |
| `limit` | int | `500` | Max records (safety cap) |
| `offset` | int | `0` | Records to skip |
| `profile` | string | *(default)* | Target profile |

```python
export_records(
    model="res.partner",
    domain="[('active', '=', True)]",
    fields="id,name,country_id/id"
)
```

---

## `import_records`

Updates records with matching External IDs; creates new ones otherwise.

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name |
| `fields` | string | Comma-separated field names |
| `rows` | string | JSON array of dicts |
| `profile` | string | Target profile |

```python
import_records(
    model="res.partner",
    fields="id,name,phone",
    rows='[{"id": "base.res_partner_1", "name": "Updated", "phone": "12345"}]'
)
```

---

## `execute_kw`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `method` | string | *(required)* | Method to execute |
| `args` | string | `[]` | Positional args (JSON array) |
| `kwargs` | string | `{}` | Keyword args (JSON object) |
| `profile` | string | *(default)* | Target profile |

```python
execute_kw(model="sale.order", method="action_confirm", args="[[42]]")
```

---

## `list_models`

```python
list_models(search="partner", profile="prod")
```

---

## `list_fields`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | *(required)* | Model name |
| `attributes` | string | `""` | Comma-separated attributes: `string,type` for compact (~5KB), default returns `string,type,required,help` (~41KB) |
| `profile` | string | *(default)* | Target profile |

```python
# Full metadata (default)
list_fields(model="account.move", profile="prod")

# Compact — only field names and types (~8x smaller)
list_fields(model="account.move", attributes="string,type", profile="prod")
```

---

## `get_version`

```python
get_version(profile="prod")
```

---

## Domain Syntax

| Natural Language | Domain |
|------------------|--------|
| name contains "John" | `[('name', 'ilike', 'John')]` |
| state is "sale" | `[('state', '=', 'sale')]` |
| amount > 1000 | `[('amount_total', '>', 1000)]` |
| date after 2024-01-01 | `[('create_date', '>=', '2024-01-01')]` |
| Mexico or USA | `['\|', ('country_id.code', '=', 'MX'), ('country_id.code', '=', 'US')]` |

## Error Responses

All tools return JSON. On error, the response contains an `error` key:

```json
{"error": "Profile 'staging' not found."}
```

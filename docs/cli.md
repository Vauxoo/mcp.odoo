# CLI Reference

Complete reference for every CLI command provided by `odoo-mcp`.
All commands output JSON to stdout and are pipeable with `jq`.

!!! tip "Global options"
    All data commands accept `--profile / -p` to target a specific environment
    (uses the default profile if omitted).

---

## Profile Management

### `add-profile`

Interactive wizard to register a new Odoo instance.

```bash
# Interactive mode
odoo-mcp add-profile

# Non-interactive (all flags)
odoo-mcp add-profile \
  --name prod \
  --url https://odoo.example.com \
  --database mydb \
  --user admin \
  --password secret
```

### `list-profiles`

```bash
odoo-mcp list-profiles          # human-readable
odoo-mcp list-profiles --json   # JSON array
```

### `edit-profile`

Only the specified fields are updated; others remain unchanged.

```bash
odoo-mcp edit-profile prod --url https://new.example.com
```

### `remove-profile`

```bash
odoo-mcp remove-profile staging
```

### `set-default`

```bash
odoo-mcp set-default prod
```

### `test`

```bash
odoo-mcp test -p prod
```

### `run` — Start the MCP Server

```bash
odoo-mcp run           # all profiles available
odoo-mcp run -p prod   # locked to a single profile
```

---

## Data Operations

### `search-read`

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--model` | `-m` | *(required)* | Model name |
| `--domain` | `-d` | `[]` | Filter domain |
| `--fields` | `-f` | all | Comma-separated fields |
| `--limit` | `-l` | `100` | Max records |
| `--offset` | | `0` | Records to skip |
| `--order` | | `""` | Sort order |

Returns a **pagination envelope** with `records`, `total`, `has_more`, `next_offset`.

```bash
odoo-mcp search-read -m res.partner \
  --domain "[('is_company', '=', True)]" \
  --fields "name,email,phone" \
  --limit 10 \
  -p prod
```

### `write`

```bash
odoo-mcp write -m res.partner \
  --ids "1,2,3" \
  --values '{"phone": "+52 555 1234"}' \
  -p prod
```

### `create`

```bash
odoo-mcp create -m res.partner \
  --values '{"name": "Alice", "email": "alice@example.com"}' \
  -p prod
```

### `export-records`

Native Odoo `export_data`. Returns a **pagination envelope**.
Use `field/id` syntax for External IDs of relational fields.

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--model` | `-m` | *(required)* | Model name |
| `--fields` | `-f` | `id,name` | Fields to export |
| `--domain` | `-d` | `[]` | Filter domain |
| `--limit` | `-l` | `500` | Max records |
| `--offset` | | `0` | Records to skip |

```bash
odoo-mcp export-records -m res.partner \
  --fields "id,name,country_id/id" \
  --domain "[('active', '=', True)]" \
  -p prod
```

### `import-records`

Native Odoo `load`. Updates records with matching External IDs; creates new ones otherwise.

```bash
odoo-mcp import-records -m res.partner \
  --fields "id,name,phone" \
  --rows '[{"id": "base.res_partner_1", "name": "Updated", "phone": "12345"}]' \
  -p prod
```

### `execute-kw`

```bash
# Confirm a sale order
odoo-mcp execute-kw -m sale.order \
  --method action_confirm \
  --args "[[42]]" \
  -p prod

# Send an email with kwargs
odoo-mcp execute-kw -m mail.mail \
  --method send \
  --args "[[123]]" \
  --kwargs '{"force_send": true}' \
  -p prod
```

### `get-version`

```bash
odoo-mcp get-version -p prod
```

### `list-models`

```bash
odoo-mcp list-models --search partner -p prod
```

### `list-fields`

```bash
odoo-mcp list-fields -m account.move -p prod
```

---

## Practical Examples

### Pipe with `jq`

```bash
# Get only company names
odoo-mcp search-read -m res.partner \
  -d "[('is_company','=',True)]" -f "name" \
  | jq '.records[].name'
```

### Export → Import across environments

```bash
# Export from staging
odoo-mcp export-records -m product.template \
  -f "id,name,list_price" -p staging > products.json

# Import to prod
odoo-mcp import-records -m product.template \
  -f "id,name,list_price" \
  -r "$(cat products.json | jq '.records')" \
  -p prod
```

### Script: confirm all draft sale orders

```bash
#!/bin/bash
ORDERS=$(odoo-mcp search-read -m sale.order \
  -d "[('state','=','draft')]" -f "id" -p prod \
  | jq '[.records[].id]')
odoo-mcp execute-kw -m sale.order \
  --method action_confirm --args "[$ORDERS]" -p prod
```

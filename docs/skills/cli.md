# CLI Commands Reference

This reference documents every CLI command provided by `odoo-mcp`. Use this when interacting with Odoo instances directly from the terminal or in automation scripts.

---

## Global Options

All data commands accept:

| Flag | Short | Description |
|------|-------|-------------|
| `--profile` | `-p` | Target profile name (uses default if omitted) |
| `--help` | | Show command help and usage |

---

## Profile Management

### `add-profile` — Register a New Instance

Interactive wizard to add Odoo connection credentials.

```bash
# Interactive mode
odoo-mcp add-profile

# Non-interactive mode
odoo-mcp add-profile --name prod --url https://odoo.example.com --database mydb --user admin --password secret
```

| Flag | Description |
|------|-------------|
| `--name` | Profile name |
| `--url` | Odoo instance URL |
| `--database` | Database name |
| `--user` | Login username |
| `--password` | Login password |
| `--test` | Test connection before saving |

---

### `list-profiles` — Show Configured Profiles

```bash
odoo-mcp list-profiles
```

Output: JSON array with name, URL, database, and default status for each profile.

---

### `edit-profile` — Modify an Existing Profile

```bash
odoo-mcp edit-profile --name prod --url https://new-url.example.com
```

Only the specified fields are updated; others remain unchanged.

---

### `remove-profile` — Delete a Profile

```bash
odoo-mcp remove-profile --name staging
```

---

### `set-default` — Set the Default Profile

```bash
odoo-mcp set-default prod
```

---

### `test` — Test Connection

```bash
odoo-mcp test -p prod
```

Verifies that the stored credentials can connect to the Odoo instance.

---

### `run` — Start the MCP Server

```bash
# Start with all profiles available
odoo-mcp run

# Lock to a specific profile
odoo-mcp run -p prod
```

---

## Odoo Data Operations

All data commands output JSON to stdout and can be piped or composed with other CLI tools (`jq`, `xargs`, etc.).

### `search-read` — Query Records

```bash
odoo-mcp search-read -m res.partner \
  --domain "[('is_company', '=', True)]" \
  --fields "name,email,phone" \
  --limit 10 \
  --order "name asc" \
  -p prod
```

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--model` | `-m` | *(required)* | Model name |
| `--domain` | `-d` | `[]` | Odoo domain filter |
| `--fields` | `-f` | all | Comma-separated field names |
| `--limit` | `-l` | `100` | Max records |
| `--offset` | `-o` | `0` | Records to skip |
| `--order` | | `""` | Sort order |

---

### `write` — Update Records

```bash
odoo-mcp write -m res.partner \
  --ids "1,2,3" \
  --values '{"phone": "+52 555 1234"}' \
  -p prod
```

| Flag | Short | Description |
|------|-------|-------------|
| `--model` | `-m` | Model name |
| `--ids` | `-i` | Record IDs (comma-separated or JSON array) |
| `--values` | `-v` | JSON object with field values |

---

### `create` — Create a Record

```bash
odoo-mcp create -m res.partner \
  --values '{"name": "Alice", "email": "alice@example.com"}' \
  -p prod
```

| Flag | Short | Description |
|------|-------|-------------|
| `--model` | `-m` | Model name |
| `--values` | `-v` | JSON object with field values |

---

### `export-records` — Native Export

Uses Odoo's `export_data` — returns clean array of dicts with External IDs.

```bash
odoo-mcp export-records -m res.partner \
  --fields "id,name,country_id/id" \
  --domain "[('active', '=', True)]" \
  -p prod
```

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--model` | `-m` | *(required)* | Model name |
| `--fields` | `-f` | `id,name` | Comma-separated fields |
| `--domain` | `-d` | `[]` | Search domain |

> **Tip:** Use `field/id` syntax to get External IDs of relational fields.

---

### `import-records` — Native Import (Bulk)

Uses Odoo's `load` — updates records with matching External IDs, creates new ones otherwise.

```bash
odoo-mcp import-records -m res.partner \
  --fields "id,name,phone" \
  --rows '[{"id": "base.res_partner_1", "name": "Updated", "phone": "12345"}]' \
  -p prod
```

| Flag | Short | Description |
|------|-------|-------------|
| `--model` | `-m` | Model name |
| `--fields` | `-f` | Comma-separated field names matching the data |
| `--rows` | `-r` | JSON array of dicts |

---

### `execute-kw` — Execute Any Method

```bash
# Confirm a sale order
odoo-mcp execute-kw -m sale.order \
  --method action_confirm \
  --args "[[42]]" \
  -p prod

# Send an email
odoo-mcp execute-kw -m mail.mail \
  --method send \
  --args "[[123]]" \
  --kwargs '{"force_send": true}' \
  -p prod
```

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--model` | `-m` | *(required)* | Model name |
| `--method` | | *(required)* | Method to call |
| `--args` | `-a` | `[]` | Positional args (JSON array) |
| `--kwargs` | `-k` | `{}` | Keyword args (JSON object) |

---

### `get-version` — Server Version

```bash
odoo-mcp get-version -p prod
```

Returns version info dict from the Odoo server.

---

### `list-models` — Discover Models

```bash
odoo-mcp list-models --search partner -p prod
```

| Flag | Short | Description |
|------|-------|-------------|
| `--search` | `-s` | Filter models by name or technical name |

---

### `list-fields` — Inspect Model Schema

```bash
odoo-mcp list-fields -m account.move -p prod
```

| Flag | Short | Description |
|------|-------|-------------|
| `--model` | `-m` | Model name to inspect |

---

## Composability Examples

### Pipe with `jq`

```bash
# Get just names of companies
odoo-mcp search-read -m res.partner -d "[('is_company','=',True)]" -f "name" | jq '.[].name'

# Count records
odoo-mcp search-read -m sale.order -d "[('state','=','sale')]" -f "id" -l 0 | jq length
```

### Export → Transform → Import

```bash
# Export from staging, import to prod
odoo-mcp export-records -m product.template -f "id,name,list_price" -p staging > products.json
cat products.json | odoo-mcp import-records -m product.template -f "id,name,list_price" -r "$(cat products.json)" -p prod
```

### Script automation

```bash
#!/bin/bash
# Confirm all draft sale orders
ORDERS=$(odoo-mcp search-read -m sale.order -d "[('state','=','draft')]" -f "id" -p prod | jq '[.[].id]')
odoo-mcp execute-kw -m sale.order --method action_confirm --args "[$ORDERS]" -p prod
```

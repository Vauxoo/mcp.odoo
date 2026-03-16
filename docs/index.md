# Odoo MCP Multi

Welcome to the documentation for **Odoo MCP Multi**, an MCP (Model Context Protocol) Server for connecting AI assistants (Antigravity, Claude Desktop, Cursor, VS Code) to multiple Odoo instances.

## Features

- **Multi-profile management**: Store credentials for multiple environments (`prod`, `staging`, `dev`)
- **Multi-protocol**: JSON-RPC (8.0+), JSON2 (19.0+), XML-RPC (legacy) — auto-detected
- **10 MCP tools**: `search_read`, `write`, `create`, `export_records`, `import_records`, `execute_kw`, `list_models`, `list_fields`, `list_available_profiles`, `get_version`
- **Full CLI parity**: Every MCP tool is also a CLI command — same shared logic, no duplication
- **Secure by default**: Credentials stored in `~/.config/odoo-mcp/` with `600` permissions

## Architecture

```
cli.py (Click) ──▶ operations.py (shared logic) ◀── server.py (MCP tools)
                           │
                  ┌────────┴────────┐
                  │    utils.py     │
                  │    config.py    │
                  └─────────────────┘
```

## Getting Started

Check out the [README on Git](https://git.vauxoo.com/nhomar/mcp.odoo) for quick setup instructions and how to integrate with your preferred AI editor.

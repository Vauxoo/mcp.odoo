# Odoo MCP Multi

The **most tested, documented, and production-ready** MCP server for Odoo.
Connects any MCP client (Antigravity, Claude Desktop, Cursor, VS Code) to
**multiple Odoo instances simultaneously** — automatic protocol detection,
secure credential storage, 70%+ test coverage, and full CLI parity.

## Features

- **Multi-profile management**: Store credentials for multiple environments (`prod`, `staging`, `dev`).
- **Secure by default**: Credentials stored in `~/.config/odoo-mcp/` with `600` permissions.
- **Multi-protocol**: JSON-RPC (8.0+), JSON2 (19.0+), XML-RPC (legacy) — auto-detected.
- **10 MCP tools**: `search_read`, `write`, `create`, `export_records`, `import_records`,
  `execute_kw`, `list_models`, `list_fields`, `list_available_profiles`, `get_version`.
- **Full CLI parity**: Every MCP tool is also a CLI command — same shared logic (DRY).
- **Pagination envelope**: `search_read` and `export_records` return `total`, `has_more`,
  and `next_offset` so agents always know when to fetch more.

## Architecture

```text
cli.py (Click) ──▶ operations.py (shared logic) ◀── server.py (MCP tools)
                           │
                  ┌────────┴────────┐
                  │    utils.py     │
                  │    config.py    │
                  └─────────────────┘
```

All data operations flow through `operations.py`, ensuring CLI and MCP tools always
behave identically — no duplication, no drift.

## Quick Install

=== "macOS"

```bash
brew install pipx
pipx install odoo-mcp-multi
odoo-mcp add-profile
odoo-mcp run
```

=== "Linux"

```bash
pip install pipx
pipx install odoo-mcp-multi
odoo-mcp add-profile
odoo-mcp run
```

=== "Windows"

```powershell
winget install Python.Python.3.12
# Open a new terminal
pip install pipx && pipx ensurepath
# Open another new terminal
pipx install odoo-mcp-multi
odoo-mcp add-profile
odoo-mcp run
```

## Copy-Paste Prompt for AI Clients

Paste this block verbatim into Antigravity, Claude, or Cursor:

```text
Install & configure the Odoo MCP server. Run these steps:

1. Install: brew install pipx && pipx install odoo-mcp-multi  (macOS)
             pip install pipx && pipx install odoo-mcp-multi   (Linux)
2. Add a profile: odoo-mcp add-profile
3. Test connection: odoo-mcp test
4. Add to your MCP config:
   { "mcpServers": { "odoo": { "command": "odoo-mcp", "args": ["run"] } } }
5. Restart your AI client.
```

## MCP Client Config Paths

| Client | macOS | Linux | Windows |
|--------|-------|-------|---------|
| **Antigravity** | `~/.gemini/antigravity/mcp_config.json` | same | `%USERPROFILE%\.gemini\antigravity\mcp_config.json` |
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Cursor** | `.cursor/mcp.json` | same | same |
| **VS Code** | `.vscode/mcp.json` | same | same |

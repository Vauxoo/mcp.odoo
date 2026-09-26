# Odoo MCP Multi

<p align="center">
  <img src="https://git.vauxoo.com/ai/mcp.odoo/-/raw/main/docs/banner.png" alt="Odoo MCP — Talk to Odoo like Jarvis" width="100%">
</p>

[![coverage](https://git.vauxoo.com/ai/mcp.odoo/badges/main/coverage.svg)](coverage/)

The **most tested, documented, and production-ready** MCP server for Odoo.
Connects any MCP client (Antigravity, Claude Desktop, Cursor, VS Code) to
**multiple Odoo instances simultaneously** — automatic protocol detection,
secure credential storage, 86%+ test coverage, and full CLI parity.

## Features

- **Multi-profile management**: Store credentials for multiple environments (`prod`, `staging`, `dev`).
- **Secure by default**: Credentials stored in `~/.config/odoo-mcp/` with `600` permissions.
- **Multi-protocol**: JSON-RPC (8.0+), JSON2 (19.0+), XML-RPC (legacy) — auto-detected.
- **13 MCP tools**: `search_read`, `search_count`, `write`, `unlink`, `create`, `export_records`, `import_records`,
  `execute_kw`, `list_models`, `list_fields`, `list_available_profiles`, `get_version`, `get_financial_report`.
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

Any of these works — use the installer you already have. All four are tested in
CI on every merge request and against PyPI after every release.

=== "uv"

```bash
uv tool install odoo-mcp-multi
uv tool update-shell   # then open a NEW terminal
odoo-mcp add-profile
odoo-mcp run
```

=== "pipx"

```bash
pipx install odoo-mcp-multi
pipx ensurepath        # then open a NEW terminal
odoo-mcp add-profile
odoo-mcp run
```

=== "uvx"

```bash
# Nothing to install: the MCP client runs it on demand.
uvx --from odoo-mcp-multi odoo-mcp add-profile
# MCP config: "command": "uvx", "args": ["--from", "odoo-mcp-multi", "odoo-mcp", "run"]
```

=== "pip"

```bash
pip install odoo-mcp-multi   # inside an environment you manage
odoo-mcp add-profile
odoo-mcp run
```

!!! note "The extra PATH step"
    `uv tool` and `pipx` install `odoo-mcp` into `~/.local/bin`, which is usually not
    on `PATH`: right after installing, `odoo-mcp` is "not found". Run
    `uv tool update-shell` / `pipx ensurepath` and open a new terminal, or use the
    absolute path (`uv tool dir --bin`, `pipx environment --value PIPX_BIN_DIR`).
    GUI MCP clients on macOS do not read shell rc files — give them the absolute path.
    `odoo-mcp upgrade` picks the right upgrade command for whichever installer you used.

## Copy-Paste Prompt for AI Clients

Paste this block verbatim into Antigravity, Claude, or Cursor:

```text
Install & configure the Odoo MCP server. Run these steps:

1. Install with the tool I already have (any is fine):
   uv tool install odoo-mcp-multi && uv tool update-shell
   pipx install odoo-mcp-multi && pipx ensurepath
   pip install odoo-mcp-multi   (inside an environment I manage)
   If `odoo-mcp` is then "not found", open a new terminal or use its absolute path.
2. Add a profile: odoo-mcp add-profile
3. Test connection: odoo-mcp test
4. Add to your MCP config:
   { "mcpServers": { "odoo": { "command": "odoo-mcp", "args": ["run"] } } }
   (with uvx: "command": "uvx", "args": ["--from", "odoo-mcp-multi", "odoo-mcp", "run"])
5. Restart your AI client.
```

## MCP Client Config Paths

| Client | macOS | Linux | Windows |
|--------|-------|-------|---------|
| **Antigravity** | `~/.gemini/antigravity/mcp_config.json` | same | `%USERPROFILE%\.gemini\antigravity\mcp_config.json` |
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Cursor** | `.cursor/mcp.json` | same | same |
| **VS Code** | `.vscode/mcp.json` | same | same |

# AGENT DIRECTIVE: SANDBOX EXECUTION RAIL

[ERROR SIGNATURE]

- "Fatal Python error: init_import_site"
- "PermissionError: .../pyvenv.cfg"

[ROOT CAUSE]
CPython venv bootstrap requires read access to `pyvenv.cfg` outside workspace boundaries.

[LEAST-PRIVILEGE TARGET PATHS]

- pipx: ~/.local/pipx/venvs/odoo-mcp-multi/
- uv:   ~/.local/share/uv/tools/odoo-mcp-multi/

[HARNESS-SPECIFIC RESOLUTION - ZERO RETRY LOOPS]

- Antigravity: Rerun with `BypassSandbox: true` OR `ask_permission(Action="read_file", Target="~/.local/pipx/venvs/odoo-mcp-multi/")`.
- Claude Code / Claude: Request terminal execution approval or read grant for the specific venv path.
- Codex / Cursor / Windsurf / OpenHands / Aider: Request user sandbox permission for the narrow venv path or execute in unsandboxed shell.

[STRICT RULE]
On signature match: IMMEDIATELY execute resolution. DO NOT run diagnostic probes (`cat`, `ls`, `grep`), DO NOT retry in sandboxed shell, DO NOT request broad root permissions (`~/.local` or `/*`).

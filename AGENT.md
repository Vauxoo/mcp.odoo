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

---

## REPOSITORY GOVERNANCE

This repository is a **Package-first Executor** in the Vauxoo agent ecosystem:
its release identity belongs to the published PyPI package `odoo-mcp-multi`,
not to the repository. Three consequences look like rule violations until you
know the class, and none of them should be "fixed":

- `.claude-plugin/plugin.json` **declares a `version`**, written by
  `[[tool.bumpversion.files]]`. Every other hub is forbidden to carry that key.
- There is **no root `plugin.json`** — the Antigravity manifest lives inside
  the package tree, at `odoo_mcp_multi/plugins/odoo-mcp/plugin.json`.
- The repository is **not named `agents-<domain>`**, unlike every other hub. It
  is named after the package it publishes, and renaming it would break
  `pip install`, the PyPI project URL and every documented MCP configuration.

Membership is re-measured on every ecosystem audit, never granted by a list.
The clause that matters most: the package version and the manifest version must
AGREE. If they drift apart the class stops protecting this repository and the
fleet audit reports a P1.

Releases are **opt-in**: no `[patch]`/`[minor]`/`[major]` marker in a pushed
commit means nothing is released. See `.agents/rules/release_workflow.md` (the
authority) and `PREPARE_RELEASE.md`.

Details: `.claude-plugin/README.md`, plus `ARCHITECTURE.md` and
`decisions/bp-2026-08-marketplace-compliance.md` §7 in `ai/lama-su-architect`.

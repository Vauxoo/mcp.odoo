# Plugin manifests — odoo-mcp

## Why this repository looks different from every other hub

`ai/mcp.odoo` is a **Package-first Executor**. It inherits the whole Executor
rulebook of the Vauxoo agent ecosystem and subtracts only what its definition
displaces: its release identity belongs to the published PyPI package
`odoo-mcp-multi`, not to the repository. The plugin is one face of that
package.

Three things follow, and each of them looks like a violation until you know
the class:

**`.claude-plugin/plugin.json` declares a `version`.** Everywhere else in this
ecosystem that key is a defect — `ai/marketplace` does not copy it into the
catalog entry, so Claude Code reads the repository's own manifest and a
declared version makes installs track version bumps instead of pushes. Here
the key is written by `[[tool.bumpversion.files]]` in `pyproject.toml` on every
release. The package owns the version; the manifest mirrors it *because the
same command writes both*, which is the one arrangement where a mirror cannot
drift silently.

**There is no root `plugin.json`.** The Antigravity manifest lives at
`odoo_mcp_multi/plugins/odoo-mcp/plugin.json`, inside the package tree, so it
travels with the installed package. It is also the only manifest in the whole
ecosystem that was schema-conformant before 2026-08-09: it declares `$schema`
and carries nothing the closed Antigravity schema forbids.

**The repository is not named `agents-<domain>`.** Every hub follows that
pattern; this one is named after the package it publishes, because the package
is the thing that exists in the world and the plugin is downstream of it.
Renaming it to fit the hub convention would break `pip install`, the PyPI
project URL and every documented MCP configuration.

## What is NOT displaced

Membership in the class is measured on every audit run, not granted once. Four
clauses must hold together: a root package manifest, a bump target on
`.claude-plugin/plugin.json`, no vendored `.qa-tools/auto-release.sh`, and —
the clause that makes the classification revocable — the package version and
the manifest version **agreeing today**. Let them drift apart and the
ecosystem's fleet audit reports a P1, because at that point the bump has
stopped reaching the manifest that ships to every install.

Everything else applies here exactly as it does to any other hub: skills carry
evals, descriptions open with "Use this skill when…", the release chain is
verified by the job rather than by the tag, and `sync-qa-tools.sh` refuses this
repository as a sync target by design rather than by accident.

See `ARCHITECTURE.md` and `decisions/bp-2026-08-marketplace-compliance.md` §7
in `ai/lama-su-architect`.

---
name: "odoo-module-deps"
description: "Use this skill to analyze the module dependency tree of an Odoo instance and generate a migration-priority report. Triggers on: 'module dependencies', 'dependency tree', 'migration order', 'module priority', 'which modules to migrate first', 'dependency levels'."
last_validated: 2026-05-09
---

# Odoo Module Dependency Tree Analyzer

Generates a priority-sorted module list from any Odoo instance. Modules at
Level 1 have no custom dependencies — migrate them first. Higher levels
depend on lower ones.

## When to use

- Planning a version migration (e.g., 16.0 → 18.0)
- Auditing which custom modules exist in an instance
- Understanding the dependency chain between modules
- Identifying leaf modules vs. core infrastructure modules

## Prerequisites

- `odoo-mcp-multi` installed with at least one profile configured
- The profile must have read access to `ir.module.module`

## Usage

### Quick run

```bash
python /path/to/odoo_mcp_multi/skills/odoo-module-deps/scripts/module_deps.py --profile <profile_name>
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--profile`, `-p` | *(required)* | Odoo profile to analyze |
| `--format`, `-F` | `csv` | Output format: `csv`, `table`, or `json` |
| `--include-native` | off | Include native Odoo modules in the output |
| `--extra-native` | *(none)* | Additional module names to treat as native (repeatable) |

### Examples

```bash
# CSV output (default) — pipe to file
python module_deps.py -p vauxoo > deps_vauxoo.csv

# Markdown table — good for pasting in issues/docs
python module_deps.py -p vauxoo -F table

# JSON — for programmatic processing
python module_deps.py -p vauxoo -F json

# Include native modules (normally filtered out)
python module_deps.py -p vauxoo --include-native

# Mark extra modules as native (project-specific exclusions)
python module_deps.py -p vauxoo --extra-native my_custom_base --extra-native another_module
```

## How it works

1. **Fetches data** via `odoo-mcp` operations (no subprocess, direct Python import):
   - All installed modules from `ir.module.module` (name, author)
   - All dependency records from `ir.module.module.dependency`

2. **Filters native modules** (unless `--include-native`):
   - Author contains "Odoo S.A.", "Odoo", or "Odoo SA"
   - Name matches `l10n_XX` pattern (country localizations)
   - Name is in the built-in exclusion list (e.g., `sale_subscription`)

3. **Builds the dependency graph** client-side and computes levels via BFS from `base`:
   - Level 1: modules that only depend on `base` / native modules
   - Level N: modules whose deepest dependency is at Level N-1
   - Unreachable modules (not connected to `base`) go in the last level

4. **Outputs the report** sorted by level, then alphabetically within each level.

## Output interpretation

| Level | Meaning | Migration strategy |
|-------|---------|-------------------|
| 1 | Leaf dependencies — no custom modules depend on them | Migrate first, can be done independently |
| 2-3 | Mid-tier — depend on Level 1 modules | Migrate after their dependencies |
| N (highest) | Core infrastructure — many modules depend on them | Migrate last, most impactful |

## Customization

### Native module exclusion

The script has a built-in `DEFAULT_NATIVE_NAMES` set for common edge cases
(modules that aren't authored by Odoo but should be excluded during migration
planning). Use `--extra-native` to add project-specific exclusions without
modifying the script.

### Integration with migration workflows

```bash
# Generate the report and attach to a GitLab issue
python module_deps.py -p prod -F table | glab issue comment 42 --repo myorg/instance -F -

# Compare two environments
diff <(python module_deps.py -p staging) <(python module_deps.py -p prod)
```

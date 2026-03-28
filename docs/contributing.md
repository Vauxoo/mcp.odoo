# Contributing

## Development Setup

```bash
git clone https://git.vauxoo.com/nhomar/mcp.odoo.git
cd mcp.odoo
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest                          # all tests with coverage
pytest tests/test_operations.py # single file
pytest -k "search_read"         # by name pattern
```

Coverage target: **70%+**. Tests live in `tests/` and use `pytest` with `unittest.mock`.

## Code Quality

```bash
ruff check odoo_mcp_multi/     # lint
ruff format odoo_mcp_multi/    # format
markdownlint-cli2 "**/*.md"    # markdown lint
```

The CI blocks on all three. Run them locally before pushing.

## Commit Message Convention

| Prefix | Meaning |
|--------|---------|
| `[IMP]` | Improvement / new feature |
| `[FIX]` | Bug fix |
| `[REF]` | Refactor (no behavior change) |
| `[ADD]` | New file or resource |
| `[REM]` | Removal |
| `[CHG]` | Configuration / tooling change |

### Release Markers (opt-in model)

**By default, merging to `main` does NOT create a release.**
To trigger one, add exactly one marker anywhere in a commit message of the push:

| Marker | Effect |
|--------|--------|
| *(none)* | No release — safe to merge freely |
| `[patch]` | Patch: `0.4.1 → 0.4.2` |
| `[minor]` | Minor: `0.4.x → 0.5.0` |
| `[major]` | Major: `0.4.x → 1.0.0` |

Examples:

```text
[IMP] server: Add new tool for attachments [patch]
[IMP] cli: Breaking change in profile format [major]
[FIX] config: Fix typo in error message        ← no release
```

## Release Process

Releases are fully automated and **opt-in**. After a MR merges to `main`:

1. CI runs lint + test.
2. If no `[patch|minor|major]` marker is found → pipeline exits cleanly, no release.
3. If a marker is found → `auto-release` bumps the version, commits with `[skip ci]`,
   pushes a tag, and triggers `publish:pypi` and `publish:gitlab`.

You never need to run `bump-my-version` manually.

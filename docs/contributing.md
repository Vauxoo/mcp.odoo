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

### Bump Level Trailers

Append to any commit in your branch to control the release bump:

| Trailer | Effect |
|---------|--------|
| *(none)* | Patch: `0.3.x → 0.3.x+1` |
| `[minor]` | Minor: `0.3.x → 0.4.0` |
| `[major]` | Major: `0.3.x → 1.0.0` |
| `[skip release]` | No release for **this push** |

Example:

```text
[IMP] server: Stabilize public API for 1.0 [major]
```

## Release Process

Releases are fully automated. After a MR merges to `main`:

1. CI runs lint + test.
2. `auto-release` job bumps the version, commits with `[skip ci]`, and pushes a tag.
3. `publish:pypi` and `publish:gitlab` jobs deploy to PyPI and the GitLab package registry.

You never need to run `bump-my-version` manually.

# Release Preparation Guide

This guide describes the release process for `odoo-mcp-multi`. Releases are **automated by CI** on every merge to main — you should rarely need to release manually.

## Automated Release (Default)

When a Merge Request is merged to `main`, the CI pipeline automatically:

1. Runs `lint` and `test`
2. Determines the bump level (see table below)
3. Runs `bump-my-version` to update `pyproject.toml`, `__init__.py`, and `test_basic.py`
4. Commits the version bump and creates a git tag
5. Pushes the tag, triggering `publish:pypi` and `publish:gitlab` jobs
6. Builds the mkdocs pages

### Bump Level Markers

The CI is **commit-format agnostic** — it does NOT read `[FIX]`, `[ADD]`, or any prefix convention. Instead, it uses explicit markers in commit messages:

| Marker | Bump | Example |
|--------|------|---------|
| *(none)* | **patch** (default) | `0.3.0 → 0.3.1` |
| `[minor]` | **minor** | `0.3.1 → 0.4.0` |
| `[major]` | **major** | `0.4.0 → 1.0.0` |
| `[skip release]` | **none** | No version bump, no publish |

The CI reads **all commit messages since the last tag**. If any commit contains `[major]`, it wins. Otherwise, `[minor]` wins. Otherwise, it defaults to `patch`.

### Usage Examples

```bash
# Normal fix — auto patch release
git commit -m "[FIX] cli: Correct argument parsing for export-records"

# New feature — explicitly mark minor
git commit -m "[ADD] server: Add bulk delete tool [minor]"

# Docs-only change — skip release
git commit -m "[IMP] docs: Update installation guide [skip release]"

# Breaking change — explicitly mark major
git commit -m "[REF] config: Change profile format to YAML [major]"
```

### CI Variable Required

The `auto-release` job requires a **Project Access Token** stored as CI variable `RELEASE_TOKEN`:

1. Go to **Settings → Access Tokens** → Create token with `write_repository` scope
2. Go to **Settings → CI/CD → Variables** → Add `RELEASE_TOKEN` with the token value
3. Mark it as **Protected** and **Masked**

---

## Manual Release (Fallback)

Only use this if the CI auto-release is not configured or fails.

### 1. Verify tests

```bash
pytest
```

### 2. Verify installation

```bash
pip install -e .
```

### 3. Run Formatting and Linting

```bash
ruff format odoo_mcp_multi/ tests/
ruff check odoo_mcp_multi/ tests/ --fix
```

### 4. Synchronize Documentation (⚠️ CRITICAL — do NOT skip)

> **This step catches feature documentation drift.** Changes often land in code and CHANGELOG but never make it to the README or mkdocs.

#### 4a. README.md

Compare the **Features**, **CLI Operations**, and **MCP Tools** sections against the actual codebase:

```bash
# Quick diff: list all CLI commands
odoo-mcp --help

# Quick diff: list all MCP tool names
grep -n '@mcp.tool' odoo_mcp_multi/server.py
```

Ensure every command and tool listed in the code appears in the README.

#### 4b. docs/ (mkdocs pages)

Review `docs/index.md` and any other pages under `docs/`. Update the feature list, architecture description, and any reference material.

#### 4c. Reference Skills

If MCP tools or CLI commands were added/removed/changed, update:
- `docs/skills/mcp.md` — MCP tool reference
- `docs/skills/cli.md` — CLI command reference

### 5. Prepare CHANGELOG.md

Update `CHANGELOG.md` with a new version section: `## [X.Y.Z] - YYYY-MM-DD`.

### 6. Bump the version

```bash
# Patch release (0.3.0 → 0.3.1)
bump-my-version bump patch

# Minor release (0.3.0 → 0.4.0)
bump-my-version bump minor
```

### 7. Push and Deploy

```bash
git push origin HEAD --tags
```

---

## Release Checklist

```
- [ ] Tests pass (`pytest`)
- [ ] Installation works (`pip install -e .`)
- [ ] Linting clean (`ruff check` + `ruff format --check`)
- [ ] README.md updated to reflect new features/commands
- [ ] docs/ pages updated
- [ ] docs/skills/ reference updated (if tools/commands changed)
- [ ] CHANGELOG.md updated with version and date
- [ ] Version bumped (auto by CI, or manually via `bump-my-version`)
- [ ] Tag pushed (auto by CI, or manually via `git push --tags`)
```

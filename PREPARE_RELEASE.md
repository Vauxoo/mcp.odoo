# Release Preparation Guide

This guide describes the release process for `odoo-mcp-multi`. Releases are automated by CI, but they are **opt-in**: merging to `main` does not release anything unless a commit in the push carries an explicit marker.

`odoo_mcp_multi` is a **Package-first Executor** in the Vauxoo agent ecosystem (see `ARCHITECTURE.md` in `ai/lama-su-architect`). Its release identity belongs to the published PyPI package, not to the repository, which is why the version lives in `pyproject.toml` and is propagated into `.claude-plugin/plugin.json` by `[[tool.bumpversion.files]]`. Every other hub in the ecosystem is forbidden to carry that key; here it is correct, and it is what defines the class.

## Automated Release (Default)

When a Merge Request is merged to `main` **and one of its commits carries a bump marker**, the CI pipeline:

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
| *(none)* | **none** | No version bump, no publish |
| `[patch]` | **patch** | `0.3.0 → 0.3.1` |
| `[minor]` | **minor** | `0.3.1 → 0.4.0` |
| `[major]` | **major** | `0.4.0 → 1.0.0` |

The CI reads the commit subjects of **the commits that arrived in this push**, not every commit since the last tag. If any carries `[major]` it wins, then `[minor]`, then `[patch]`. With no marker the job prints `No [patch|minor|major] found in push commits. Skipping release.` and exits 0.

> **Corrected 2026-08-09.** This table used to say that *(none)* meant an
> automatic patch release, and it documented a `[skip release]` marker in three
> places. Neither was ever true of this repository's CI: `.gitlab-ci.yml` states
> `Release is OPT-IN: without [patch|minor|major] we do nothing`, and the string
> `[skip release]` appears nowhere in it. `.agents/rules/release_workflow.md`
> described the real behaviour all along, so the two documents contradicted each
> other and the wrong one was the more prominent. A release guide that is
> confidently wrong is worse than none: it teaches a habit the machine does not
> honour.

### Usage Examples

```bash
# Fix worth releasing — the marker is what releases it
git commit -m "[FIX] cli: Correct argument parsing for export-records [patch]"

# New feature
git commit -m "[ADD] server: Add bulk delete tool [minor]"

# Docs-only change — no marker, so nothing is released
git commit -m "[IMP] docs: Update installation guide"

# Breaking change
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

```markdown
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

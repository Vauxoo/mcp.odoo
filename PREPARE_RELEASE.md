# Release Preparation Guide

This guide describes the standard procedure to prepare a new release of `odoo-mcp-multi` ensuring code quality, documentation consistency, and correct packaging.

## 1. Verify tests

Before releasing, always run the full test suite.
You can run this using standard `pytest`:

```bash
pytest
```

## 2. Verify installation processes
The project uses `pyproject.toml` managed by `hatchling`.
It is completely agnostic to the package manager you use. Ensure both standard methodologies work:

**Test with `uv` (fast installer):**
```bash
uv pip install -e .
```

**Test with `pip` (standard installer):**
```bash
pip install -e .
```

## 3. Run Formatting and Linting
Ensure the code is formatted to standard style rules. We use `ruff` (integrated into the Multi-Language Linting workflow).

```bash
ruff format odoo_mcp_multi/ tests/
ruff check odoo_mcp_multi/ tests/ --fix
```

## 4. Synchronize Documentation (⚠️ CRITICAL — do NOT skip)

> **This step catches feature documentation drift.** Changes often land in code and CHANGELOG but never make it to the README or mkdocs. Review each file below and update them to reflect the current state of the project.

### 4a. README.md

Compare the **Features**, **CLI Operations**, and **MCP Tools** sections against the actual codebase:

```bash
# Quick diff: list all CLI commands
odoo-mcp --help

# Quick diff: list all MCP tool names
grep -n '@mcp.tool' odoo_mcp_multi/server.py
```

Ensure every command and tool listed in the code appears in the README. If a new feature was added, **add it to the corresponding section** (Features, CLI Operations, or MCP Tools).

### 4b. docs/ (mkdocs pages)

Review `docs/index.md` and any other pages under `docs/`. Update the feature list, architecture description, and any reference material that may have changed.

### 4c. Reference Skills

If MCP tools or CLI commands were added, removed, or changed, update the reference skills in `docs/skills/`:
- `docs/skills/mcp.md` — MCP tool reference
- `docs/skills/cli.md` — CLI command reference

## 5. Prepare CHANGELOG.md
Make sure `CHANGELOG.md` is updated. 
Under `[Unreleased]`, gather the changes, and convert it to a new section, e.g., `## [0.3.0] - AAAA-MM-DD`.

## 6. Bump the version
The versioning is entirely automated via `bump-my-version`. It will seamlessly update `pyproject.toml` and `__init__.py`, and create a release commit and git tag.

**For a patch release (e.g., 0.2.0 -> 0.2.1):**
```bash
bump-my-version bump patch
```

**For a minor release (e.g., 0.2.0 -> 0.3.0):**
```bash
bump-my-version bump minor
```

## 7. Push and Deploy
Push the automatically generated commit and tag to the repository.

```bash
git push origin HEAD --tags
```

This will trigger the GitLab CI pipeline (`publish:pypi` job) that will build and publish the wheel and sdist to PyPI automatically. 
If doing it manually from your local host:
```bash
python -m build
twine upload dist/*
```

## Release Checklist (Copy-Paste)

Use this checklist in your MR or commit message:

```
- [ ] Tests pass (`pytest`)
- [ ] Installation works (`pip install -e .`)
- [ ] Linting clean (`ruff check` + `ruff format --check`)
- [ ] README.md updated to reflect new features/commands
- [ ] docs/ pages updated
- [ ] docs/skills/ reference updated (if tools/commands changed)
- [ ] CHANGELOG.md updated with version and date
- [ ] Version bumped (`bump-my-version bump minor|patch`)
- [ ] Pushed with tags (`git push origin HEAD --tags`)
```

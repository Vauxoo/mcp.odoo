# Release Preparation Guide

This guide describes the standard procedure to prepare a new release of `odoo-mcp-multi` ensuring code quality and correct packaging.

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

## 4. Prepare CHANGELOG.md
Make sure `CHANGELOG.md` is updated. 
Under `[Unreleased]`, gather the changes, and convert it to a new section, e.g., `## [0.3.0] - AAAA-MM-DD`.

## 5. Bump the version
The versioning is entirely automated via `bump-my-version`. It will seamlessly update `pyproject.toml` and `__init__.py`, and create a release commit and git tag.

**For a patch release (e.g., 0.2.0 -> 0.2.1):**
```bash
bump-my-version bump patch
```

**For a minor release (e.g., 0.2.0 -> 0.3.0):**
```bash
bump-my-version bump minor
```

## 6. Push and Deploy
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

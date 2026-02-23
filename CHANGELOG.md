# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.8] - 2026-02-23

### Fixed
- Fixed an ongoing `500 Internal Server Error` during GitLab Package Registry deployments by replacing the `license = "MIT"` string definition with a `license = {text = "MIT"}` table in `pyproject.toml`. This prevents `hatchling` from injecting the PEP 639 `License-Expression` metadata field which crashes GitLab's internal PyPI Ruby metadata parser.

## [0.2.7] - 2026-02-23

### Fixed
- Fixed a `500 Internal Server Error` during `publish:gitlab` pipeline job by preventing the use of brackets (`[Vauxoo]`) in the `pyproject.toml` author name. This bypasses a known bug in GitLab's internal Ruby `Mail::Address` parsing of PyPI metadata.
- Added `--verbose` flag to `twine upload` commands in `.gitlab-ci.yml` to improve future deployment traceability.

## [0.2.6] - 2026-02-23

### Added
- Added `CONTRIBUTING.md` to establish clear contribution, setup, and code-quality guidelines for the community.
- Added `LICENSE` file officially releasing the repository under the MIT License.

## [0.2.5] - 2026-02-23

### Changed
- Refactored `README.md` to be "SKILL friendly"—condensing excessively verbose CLI options and tool schemas into streamlined, high-density documentation tailored for AI agents.
- Updated `.gitlab-ci.yml` to implement "Option 1" for the Tag Pipeline: 
  - Attached the `pages` job to the tag-triggered pipeline for a complete view of the deployment sequence (`lint` -> `test` -> `pages` -> `publish:pypi`).
  - Reverted `publish:pypi` back to automated execution by removing `when: manual`.

## [0.2.4] - 2026-02-23

### Changed
- Converted the `publish:pypi` GitLab CI job to a manual trigger (`when: manual`) to prevent automatic deployment to PyPI when a tag is pushed.

### Added
- Added usage examples for `export_records` and `import_records` to the `README.md` documentation.

## [0.2.3] - 2026-02-23

### Fixed
- Fixed GitLab CI pipeline configuration by enabling `lint` and `test` jobs on tags, allowing `publish:pypi` to execute correctly and publish releases.

## [0.2.2] - 2026-02-23

### Fixed
- Added `tests/test_basic.py` to `bump-my-version` config to prevent hardcoded version assertions from failing the test suite post-release.

## [0.2.1] - 2026-02-23

### Fixed
- Gracefully handle `json.JSONDecodeError` in `JsonRpcClient._call` when the Odoo server returns non-JSON responses like HTML error pages, preventing the MCP server from crashing.

## [0.2.0] - 2026-02-22

### Changed
- Translated all `README.md` and documentation files to English.
- Refactored `README.md` configuration examples to use generic and anonymized placeholders instead of specific client instances.
- Updated `pyproject.toml` and `mkdocs.yml` authors and repository URLs to `nhomar [Vauxoo]` and `git.vauxoo.com`.
- Applied extensive codebase formatting and automated fixed linting issues using `ruff` (Multi-Language Linting skill).

## [0.1.0] - 2026-02-22

### Added
- Initial release of `odoo-mcp-multi`.
- Support for multiple Odoo profiles defined in `~/.config/odoo-mcp/profiles.yaml` or `~/.config/odoo-mcp/profiles.json`.
- Standard MCP tools: `list_models`, `search_read`, `read`, `create`, `write`, `execute_kw`, and `get_version`.
- Command Line Interface (CLI) to manage server output and list profiles.
- Automatic inference of database and port for seamless `.odoorc` and local `odoo` implementations.
- Robust data conversion preserving `False` to `false` and standard Python types for XML-RPC limitations.

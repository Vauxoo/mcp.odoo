# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-05-07

### Added

- New modules extracted from monolithic `utils.py`:
  - `client.py` — `BaseOdooClient`, `JsonRpcClient`, `Json2Client`, `XmlRpcClient`
  - `exceptions.py` — `OdooConnectionError`, `OdooAuthenticationError`, `OdooExecutionError`
  - `parsers.py` — `normalize_url`, `parse_domain`, `parse_fields`, `parse_version`, etc.
  - `version.py` — `get_server_version`, `detect_protocol`, protocol strategy
  - `utils.py` retained as backward-compatible re-export shim (zero breaking changes)
- `set_fallback_profile()` in `operations.py` — clean dependency injection replacing circular import hack
- Coverage contexts: `--cov-context=test` + `show_contexts=true` in HTML reports
- Unit tests for `Json2Client._build_body` and `_headers` (204 total tests, 79% coverage)

### Changed

- **Unified error-dict contract**: all 10 operations return `{success: False, error: "..."}` on failure — no operation raises exceptions to the caller
- `server.py` simplified to a pure pass-through layer — no `try/except`, single `_json()` helper
- CLI commands reduced to one-liners: `_output(op_xxx(...))` — removed 9 dead `try/except` blocks
- `_handle_error()`, `OdooAuthenticationError` and `OdooExecutionError` imports removed from CLI (dead code)
- `_call()` in `JsonRpcClient` flattened — nested try blocks eliminated, diagnostic logic extracted to `_diagnose_non_json_response()`
- `_build_body()` in `Json2Client` simplified with return-early pattern
- `create_client()` refactored with guard clause for api_key validation
- `skills install` now tracks `linked`/`failed`/`skipped` counts — only prints success when `failed == 0`, exits with code 1 on errors

### Fixed

- **Windows: `$HOME` path resolution** — `AGENT_DIRS` used `$HOME` which `os.path.expandvars` cannot resolve on Windows (uses `USERPROFILE`). Replaced with `~` and `Path.expanduser()` for cross-platform compatibility.
- **Windows: cp1252 console encoding** — Unicode `✓`/`✗` characters crash PowerShell's default cp1252 console. Added `TICK`/`CROSS` constants with automatic fallback to `[OK]`/`[FAIL]`.
- **Skills install false-success** — "Skills successfully installed" message no longer prints when symlink creation partially fails.

### Validated

- 60/60 integration tests against 4 production Odoo instances (v11.0, v16.0, v18.0, v19.0) across JSON-RPC and JSON-2 protocols:
  - 16 read operations (search-read + export-records)
  - 24 write operations (create + write + import-records)
  - 20 failure-mode tests (server down + bad credentials)
- Zero regressions between old (pipx v0.5.2) and new (local source) builds

## [0.5.2] - 2026-04-28

### Fixed

- CI runner test trigger for tag pipeline validation

## [0.5.1] - 2026-04-20

### Added

- `odoo-mcp skills` command group for agentic IDE skill discovery and installation
- Anti-bot `User-Agent` header injection to bypass WAF mechanisms on Odoo instances

## [0.5.0] - 2026-04-20

### Added

- Added support for Odoo 19+ via the new JSON-2 API (`Json2Client`).
- Added authentication support using `--api-key`.
- Added documentation for Odoo 19+ API migration and differences.

### Changed

- CI Pipeline: Releases are now opt-in via commit message tokens (`[patch]`, `[minor]`, `[major]`).
- Improved branding and SEO metadata (server name, footer, absolute URLs).
- Added markdownlint check to CI and local `pre-push` hooks.
- Set pyenv inside the pre-push hook for better environment isolation.

### Fixed

- Improved version suffix parsing and fixed JSON-2 `create` method.
- Resolved markdownlint formatting issues breaking the CI pipeline.

## [0.3.0] - 2026-03-15

### Added

- **Full CLI parity with MCP tools**: All 9 Odoo data operations are now available as CLI commands (`search-read`, `write`, `create`, `export-records`, `import-records`, `execute-kw`, `get-version`, `list-models`, `list-fields`).
- New shared `operations.py` module extracting business logic from `server.py` — both MCP and CLI call the same functions (DRY architecture).
- 54 new tests: `test_operations.py` (19 unit tests), `test_cli_commands.py` (14 CLI integration tests), `test_pre_parsed_args.py` (additional coverage). Total: **60 tests**.

### Changed

- Refactored `server.py` to thin MCP wrapper delegating to `operations.py`.
- Expanded `README.md` with full CLI data operations documentation.

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

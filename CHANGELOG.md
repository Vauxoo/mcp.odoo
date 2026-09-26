# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.17.0] - 2026-09-26

One odoo-mcp can now serve every session on your machine (`serve --auth local`, a Linux service via `odoo-mcp service install`) or remote users through OAuth (`serve`), and a profile can trust its own CA instead of `--no-verify`.

Try: instala odoo-mcp como servicio para que todas mis sesiones de claude usen un solo servidor

### Security

- A TLS certificate verification failure no longer downgrades the connection. Since 0.9.0 the XML-RPC, JSON-RPC and JSON-2 clients caught the error, set `self.verify = False` and replayed the same request, so an on-path attacker collected the password (or the `Authorization: bearer` API key) just by presenting a certificate that fails to validate, and every later call on that client stayed unverified. The three transports now propagate `OdooSSLVerificationError`. **This refuses connections that used to work**: the explicit opt-in is unchanged, so trust the CA (`SSL_CERT_FILE`) or run `odoo-mcp edit-profile <name> --no-verify`. `docs/windows-install.md` walks through the corporate-proxy case.
- `is_ssl_verification_error()` no longer loops forever on an exception chain that links back to itself.
- `edit-profile` no longer drops `protocol` and `permissions`: it rebuilt the profile from a handful of fields, so any edit — `--no-verify` included — silently turned a granular read-only profile into full access.
- The SSL error an AI agent reads now offers `--ca-bundle` first and states that `--no-verify` is a decision for a person, never one to apply automatically.

### Added

- Per-profile TLS trust, so a corporate proxy no longer forces `--no-verify`: `--ca-bundle <pem>` trusts that CA on every transport (XML-RPC, JSON-RPC, JSON-2) instead of the default store, and `--no-ssl-strict` relaxes only Python 3.13+'s `VERIFY_X509_STRICT` for a CA whose `basicConstraints` is not critical — chain and hostname are still verified. Both are on `add-profile` and `edit-profile` (`--clear-ca-bundle` undoes the first) and stored as `ca_bundle` / `ssl_strict` in `profiles.json`. Profiles that set neither behave exactly as before.
- Python 3.13 and 3.14 are now declared supported. Every pipeline installs the built wheel on a bare image for each of 3.10–3.14 and runs the whole suite against it — no test is skipped by Python version — then reports the combined line and branch coverage.
- uv (`uv tool install`), uvx, pipx and pip are documented as equal options, with the extra step uv and pipx need before `odoo-mcp` is on `PATH` and the absolute-path fallback for GUI MCP clients. CI installs the wheel with each of them on Python 3.10 and 3.14, speaks MCP to the server the way a client does and runs `odoo-mcp upgrade`; after every release, and on a schedule, it repeats that against PyPI.
- Added `odoo-mcp serve`: the same 13 tools over Streamable HTTP, with an embedded OAuth 2.1 authorization server whose consent screen authenticates against Odoo itself. Remote MCP clients connect to a URL, each user signs in with their own Odoo instance and credentials, and every tool call runs as that Odoo user under their own access rights. `odoo-mcp run` and stdio mode are unchanged.
- Added per-request credential resolution (`odoo_mcp_multi/context.py`): over HTTP the active Odoo profile comes from the authenticated token rather than a process global, so one process serves many users without their credentials crossing. `profiles.json` is not read in HTTP mode, and `list_available_profiles` returns empty so host profile names are not disclosed to remote callers.
- Added `odoo-mcp serve --auth local`: one process serves every MCP client on a workstation with the local `profiles.json`, instead of one ~60 MiB `run` process per session (80 idle processes, 5.3 GiB on a real workstation). Loopback only, no browser Origin, and a bearer token kept in a 0600 file next to `profiles.json`, so it reaches exactly the OS user stdio reaches, even on shared hosts or behind a forwarded port. Diagnosis and design from !64 by Luigys Toro.
- Added `odoo-mcp service install|status|uninstall` (Linux): runs `serve --auth local` as a systemd user service, built for how the package was installed (the environment's interpreter for pip, pipx and uv tool; `uvx --from` a pinned version for uvx), and waits until it answers before printing the client command.
- Added the `odoo-mcp http` command group (`clients`, `grants`, `revoke`, `purge`) to inspect and revoke what the HTTP server has issued. Revoking a grant also deletes the Odoo credentials stored for it.
- Added an `http` extra (`pip install 'odoo-mcp-multi[http]'`) and a `docs/http-mode.md` guide.
- Added `op_validate_credentials`, which closes the gap `op_test_connection` leaves for Odoo 19+ API keys: `Json2Client.authenticate()` is a no-op, so the key is now proven with a real read before it is accepted.

### Changed

- Tool calls sent in the same parallel batch can now run in any order, also over stdio; the bundled skills tell agents to send dependent calls one at a time.
- MCP tools now run on a worker thread instead of the event loop. FastMCP calls synchronous tools inline, so a slow Odoo RPC blocked every other request in the same process; over HTTP that also stalled the OAuth endpoints, whose clients time out in ten seconds. Also makes long stdio calls interruptible.
- `server.py` exposes a `build_server()` factory so a second transport can be configured independently. The module-level `mcp` singleton is unchanged for stdio.

### Fixed

- Over OAuth, a certificate failure told the remote user to run `odoo-mcp edit-profile --ca-bundle` or consider `--no-verify`, on a server they do not control, and the consent form could report it as "API key rejected". The user now reads why the certificate failed, that nothing was sent, and that the operator must fix it; the operator gets the host in the server log. stdio and `--auth local` keep the CLI remedy.
- The `serve` consent form accepted a password on Odoo 19+ (JSON-2) without contacting Odoo, because JSON-2 has no login call: the grant was issued and only the first tool call failed. JSON-2 sign-ins are now always proven with a real read, and a password there is refused with a message that asks for an API key.
- `odoo-mcp test` ignored the profile's `verify` setting, so it failed on a `verify: false` profile the server itself connected to.
- `odoo-mcp upgrade` works for every installer: under `uv tool install` it failed with `No module named pip`, and uvx or a uv-created venv were taken for plain pip. It also no longer mistakes an editable checkout in a uv venv for a PyPI install it could overwrite.
- The metadata cache tolerates two threads evicting the same expired entry, which used to surface as a spurious `list_models`/`list_fields` error now that tool calls run concurrently.
- The `mcp` dependency floor was `>=1.0.0`, but the server fails to import on anything older than `mcp` 1.14.0 (`issubclass() arg 1 must be a class` while registering tools). The floor is now `>=1.14.0`.
- `serve` ignored a profile's `ca_bundle` and `ssl_strict`: the timeout it sets takes a separate client-creation path that still passed the bare `verify` flag, so a profile behind a corporate CA failed over HTTP while it worked over stdio.

## [0.16.0] - 2026-09-02

The three bundled skills now ship with evals and the "Use this skill when" phrasing Claude Code matches on, and every release notifies the Vauxoo AI marketplace catalog the moment it is tagged.

Try: lista los profiles de odoo disponibles y busca los ultimos 5 partners creados

### Added

- Evals for `odoo-mcp-tools`, `odoo-mcp-cli` and `odoo-financial-reports`, written against what each skill documents rather than as boilerplate: never put a password on a command line, count before `unlink`, resolve the sandbox rail immediately instead of probing, discover model and field names instead of guessing them, keep reads bounded, and warn about report 418 on Odoo 19 before running it. The ecosystem audit had been resolving the skills directory as `<repo>/skills`, which does not exist here, so it reported a false PASS for as long as the skills existed.
- `notify_catalog` CI job: a release tag now triggers the `ai/marketplace` catalog regeneration with `SOURCE_REPO` and `SOURCE_TAG`, so the index refreshes and the Telegram announcement fires the same day. Until now the index only refreshed on the marketplace's daily schedule and no release of this package had ever been announced.

### Changed

- Skill descriptions open with "Use this skill when" instead of "Use this skill to", the phrasing the ecosystem standard requires for the harness to match them.
- CI: a new commit on a branch cancels the pipeline it supersedes, including jobs already running (`auto_cancel: interruptible`). The release, GitHub mirror, catalog notification, pages and release-notes jobs opt out so a mid-flight release is never interrupted.

### Fixed

- `PREPARE_RELEASE.md` documented a release model this CI never had: an automatic patch release on unmarked merges and a `[skip release]` marker. Releases are opt-in via `[patch]`/`[minor]`/`[major]` in a push commit, and the guide, `AGENT.md` and the bumpversion block now say so and explain why this repository, as a Package-first Executor, carries a `version` key in `.claude-plugin/plugin.json`.
- JUnit reports written by the QA scripts (`ecosystem_audit_*.xml`) are ignored; one had been committed by accident.

## [0.15.1] - 2026-08-07

odoo-mcp joined the Vauxoo AI marketplace (news from v0.15.0): one `/plugin install odoo-mcp@vauxoo-ai` brings its 3 skills plus the `odoo` MCP server, and every release now announces itself with real notes.

Try: instala el plugin odoo-mcp desde el marketplace vauxoo-ai

### Fixed

- Releases now maintain this file automatically: `bump-my-version` stamps the `[Unreleased]` section into a dated version section at release time, and a new `release-notes` CI job publishes that section as the GitLab Release description — the source the Vauxoo AI marketplace announcer reads. Until now no automation touched the changelog (versions shipped with everything stuck under Unreleased) and tags carried no Release object, so announcements degraded to a generic "Nueva versión publicada." with a dead release link.

## [0.15.0] - 2026-08-06

odoo-mcp joined the Vauxoo AI marketplace: a single `/plugin install odoo-mcp@vauxoo-ai` in Claude Code now delivers the three bundled skills plus the `odoo` MCP server, and the repository moved to the `ai` group where the catalog discovers it on its own.

### Added

- Claude Code now installs `odoo-mcp` as a standard plugin from the Vauxoo AI marketplace (`/plugin marketplace add https://git.vauxoo.com/ai/marketplace.git`, then `/plugin install odoo-mcp@vauxoo-ai`). The manifest moved to the repo root (`.claude-plugin/plugin.json`) — the only location the `ai/marketplace` catalog auto-discovers — and reaches the packaged skills through a `skills` path override, so the pip layout is untouched and remains the single source of truth.
- The Claude Code plugin registers the `odoo` MCP server (`odoo-mcp run`), so one plugin install delivers skills plus MCP tools; the pip package on `PATH` is the documented prerequisite.
- CI: `validate-plugin` job (official `claude plugin validate`) and `notify-catalog` job that triggers the marketplace catalog regeneration on default-branch pushes and release tags (activates via inherited group variables once the repo lives in the `ai` group).

### Changed

- The repository moved from `git.vauxoo.com/nhomar/mcp.odoo` to `git.vauxoo.com/ai/mcp.odoo`: the `ai` group is the only namespace the Vauxoo AI marketplace catalog scans, and living there lets CI inherit the catalog trigger variables. GitLab redirects the old URLs, but every self-reference (packaging metadata, docs, badges, MCP server instructions) now points at the canonical home so clones and issue links do not depend on redirects. Update your local remotes with `git remote set-url origin git@git.vauxoo.com:ai/mcp.odoo.git`.
- `plugins install claude` no longer copies flat skills into `~/.claude/skills`: it now offers to remove a previous flat install (which would duplicate the plugin's skills) and prints the marketplace commands. `plugins uninstall claude` still cleans up flat copies.
- `agy` is now a true alias of `antigravity` in `plugins install`/`uninstall`: both install the full plugin (manifest + skills) into `~/.gemini/config/plugins/odoo-mcp` instead of flat skills into `~/.gemini/config/skills`. Antigravity discovers the plugin tree natively, so the flat copies only duplicated skill discovery.
- Plugin installs and uninstalls for `antigravity`/`agy` now purge legacy flat skill copies left in `~/.gemini/config/skills` by pre-0.14 `agy` installs, keeping skills owned by other packages untouched.

## [0.13.0] - 2026-07-28

### Added

- Added `odoo-mcp plugins` command group (`list`, `install`, `uninstall`) to manage the bundled skills and the Antigravity `plugin.json` manifest; `skills` remains available as a full alias.
- Added `plugins uninstall <agent>`: removes the whole plugin directory for `antigravity` and only the odoo-mcp skills for flat agents, preserving foreign skills that share the directory.
- Added `agents` install target (`~/.agents/skills`), the cross-agent Agent Skills standard directory read natively by Codex, AGY, OpenCode, Kimi and Hermes.
- Added `.claude-plugin/plugin.json` manifest so the packaged plugin tree also loads as a full Claude Code plugin (`odoo-mcp@skills-dir`).
- Added skill frontmatter validation on `plugins install`: warnings (non-blocking) against the strictest cross-agent contracts — name must equal the directory name and match `^[a-z0-9]+(-[a-z0-9]+)*$`, description required and capped at 1024 chars; a test keeps the bundled skills contract-clean.
- Promoted `search_count` to a first-class MCP tool (13 tools total) and `search-count` CLI command, wired into the granular permission model. The docs advertised both while the method was only reachable via `execute_kw`.

### Changed

- Reorganized bundled agentic skills inside the `odoo_mcp_multi/plugins/odoo-mcp/` Antigravity plugin structure with a schema-compliant `plugin.json` (only `$schema`, `name`, `description` — the official schema rejects additional properties).
- `plugins install` now copies files by default — symlinks are not discovered by the Antigravity IDE, require elevated privileges on Windows, and dangle when installed from a temporary git worktree. `--symlink` keeps the previous behavior for development; re-run `install --force` after upgrading to refresh copies.
- The Antigravity plugin directory name is derived from the packaged plugin directory instead of being hardcoded in the install path.
- Moved the financial report HTML/CSS templates from the `odoo-financial-reports` skill into `odoo_mcp_multi/templates/` so the server runtime no longer depends on agent-facing skill content.

### Fixed

- Corrected install target paths verified against current agent documentation: `codex` → `~/.agents/skills`, `opencode` → `~/.config/opencode/skills`, and `gemini` replaced by `agy` → `~/.gemini/config/skills` (the Antigravity global skills directory).
- Plugin install tests now run against a sandboxed HOME; the previous tests created directories inside — and with `--force` could silently delete installed skills from — the developer's real HOME.
- Install error handling narrowed from bare `Exception` to `OSError` so programming errors surface instead of being counted as failed items.
- Documentation synchronized with the code: the 12-tool list matches `server.py` (`search_count` documented as an `execute_kw` pattern, `get_financial_report` and `unlink` added where missing), bundled skill counts, new `plugins` CLI reference section, stale skill paths, and the CI auto-release header comment.

### Removed

- Removed the `odoo-module-deps` skill from the bundled plugin: standalone tooling not native to this package (its scripts used neither the MCP server nor the CLI code paths). The bundled skills are now `odoo-mcp-tools`, `odoo-mcp-cli`, and `odoo-financial-reports`.

## [0.12.0] - 2026-07-28

### Added

- Added support for `kimi` (`~/.kimi/skills`) and `hermes` (`~/.hermes/skills`) agent managers to `odoo-mcp skills install <agent>`.

### Changed

- Lowered default `limit` of `search_read` from 100 to 25 across FastMCP tool, operations, CLI, and bundled skill guides (`odoo-mcp-tools` and `odoo-mcp-cli`). Paging via `next_offset` reaches larger sets with ~4x smaller default payload.
- Added additive `hint` key when no `fields` are passed to `search_read`, nudging callers toward explicit fields to cut token usage.
- Added token-efficiency guidance in MCP server system prompt, docstrings, and skills documentation (explicit `fields`, `format='compact'`/`csv`, small `limit` + `next_offset`, `search_count`).

### Fixed

- Fixed `odoo-mcp skills install antigravity` and `gemini` target paths to align with modern Antigravity plugin (`~/.gemini/config/plugins/odoo-mcp/skills`) and Gemini skills (`~/.gemini/config/skills`) directory structure.
- Removed hardcoded absolute file path in `odoo-financial-reports/SKILL.md` to restore skill portability across environments.
- Pinned `mcp[cli]>=1.0.0,<2.0.0` dependency to prevent breaking changes in PyPI releases of `mcp 2.0.0` from breaking CI builds.

## [0.11.0] - 2026-07-26

### Fixed

- Fixed interactive `add-profile` CLI wizard to complete prompts cleanly in terminal mode without raising errors when username is omitted for Odoo 19+ API Key auth.
- Delegated connection testing in `add-profile` directly to `op_test_connection`, enabling auto-credential migration (`password` → `api_key`) when Odoo 19+ (`json2s`) is detected.
- Guaranteed zero network calls when `--no-test` is passed to `add-profile`.
- Passed `previous_options` and `options` as named keyword arguments (`kwargs`) in `get_financial_report` to ensure robust parameter serialization on Odoo 19+ JSON-2 REST API.
- Added `*.lock` pattern to `.gitignore` to prevent untracked lockfiles from polluting working trees.

### Added

- Added portable Git worktree policy guidelines to `CONTRIBUTING.md` and `.cursorrules`.

## [0.10.0] - 2026-06-15

### Added

- Expose Odoo's financial reports (Balance Sheet, Profit & Loss, Partner Ledger, etc.) via new `get_financial_report` CLI command and MCP tool.
- Add complete test coverage for the financial reports operation, including mocking Odoo RPC calls, testing date options, company context propagation, multiple format outputs, and RPC error handling.

### Changed

- Refactored HTML report rendering to use Jinja2 templates (`financial_report.html` and `financial_report.css`), decoupling layout structure from Python logic.
- Simplified resource loading via standard Python `importlib.resources`.
- Added multi-company support to `get_financial_report` allowing reports filtering by multiple company IDs.
- Applied Vauxoo corporate design guidelines and visual brand identity (colors, typography) to HTML reports.
- Centralized version validation under `BaseOdooClient` to support Odoo 19+ singular (`get_report_information`) and Odoo 17-18 plural (`get_report_informations`) financial report RPC endpoints.

## [0.9.0] - 2026-06-11

### Added

- SSL verification option (`verify`) across all clients and configuration profiles to support self-signed certificates.
- Automated self-healing SSL fallback in XML-RPC, JSON-RPC, and JSON-2 clients when verification fails, with warning metadata returned to CLI and MCP callers.
- Tabular formatters (`compact`, `table`, `html`, `csv`) for CLI output on search-read, list-models, and list-fields.

### Changed

- Refactored `Json2Client` to dynamically inspect method signatures from `/doc-bearer` API (Odoo 19.0+) and cache them using a `_CACHE_MISS` sentinel.
- Reinforced validation of `model` and `method` parameters on `Json2Client.execute_kw` and `_build_body`.
- Broadened exception catching from `TimeoutException`/`NetworkError` to generic `RequestError` for introspection resilience.

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

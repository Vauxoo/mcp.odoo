# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-02-22

### Added
- Initial release of `odoo-mcp-multi`.
- Support for multiple Odoo profiles defined in `~/.config/odoo-mcp/profiles.yaml` or `~/.config/odoo-mcp/profiles.json`.
- Standard MCP tools: `list_models`, `search_read`, `read`, `create`, `write`, `execute_kw`, and `get_version`.
- Command Line Interface (CLI) to manage server output and list profiles.
- Automatic inference of database and port for seamless `.odoorc` and local `odoo` implementations.
- Robust data conversion preserving `False` to `false` and standard Python types for XML-RPC limitations.

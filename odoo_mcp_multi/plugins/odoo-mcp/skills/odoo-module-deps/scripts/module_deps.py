#!/usr/bin/env python3
"""Module dependency tree analyzer — CLI entry point.

Fetches installed Odoo modules and their dependencies via the `odoo-mcp`
CLI (subprocess), builds the dependency graph client-side, and outputs a
priority-sorted report where leaf modules (no dependents) appear first —
useful for planning migration order.

This script is intentionally self-contained: it uses only the Python stdlib
and relies on `odoo-mcp` being available in PATH (installed via pipx).
No imports from `odoo_mcp_multi` are needed.

Usage:
    python module_deps.py --profile vauxoo
    python module_deps.py --profile vauxoo --format table
    python module_deps.py --profile vauxoo --include-native
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Sibling library with pure graph logic (no external dependencies)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from module_deps_lib import (  # noqa: E402
    DEFAULT_NATIVE_NAMES,
    _build_graph,
    _compute_levels,
    _format_output,
    _is_native,
)


def _run_odoo_mcp(args: list[str]) -> dict:
    """Run an odoo-mcp CLI command and return parsed JSON output."""
    cmd = ["odoo-mcp", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running: {' '.join(cmd)}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def _fetch_all_pages(model: str, domain: str, fields: str, profile: str) -> list[dict]:
    """Paginate through all records via the odoo-mcp CLI."""
    all_records: list[dict] = []
    offset = 0
    limit = 500
    while True:
        data = _run_odoo_mcp(
            [
                "search-read",
                "-m",
                model,
                "--domain",
                domain,
                "--fields",
                fields,
                "--limit",
                str(limit),
                "--offset",
                str(offset),
                "-p",
                profile,
            ]
        )
        records = data.get("records", [])
        all_records.extend(records)
        if not data.get("has_more", False):
            break
        offset = data["next_offset"]
    return all_records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Odoo module dependency tree for migration planning.",
    )
    parser.add_argument("--profile", "-p", required=True, help="Odoo profile to connect to")
    parser.add_argument(
        "--format",
        "-F",
        dest="fmt",
        default="csv",
        choices=["csv", "table", "json"],
        help="Output format (default: csv)",
    )
    parser.add_argument(
        "--include-native",
        action="store_true",
        default=False,
        help="Include native Odoo modules in the output",
    )
    parser.add_argument(
        "--extra-native",
        action="append",
        default=[],
        help="Additional module names to treat as native (repeatable)",
    )
    args = parser.parse_args()

    print("Fetching installed modules...", file=sys.stderr)
    modules = _fetch_all_pages(
        model="ir.module.module",
        domain="[('state', '=', 'installed')]",
        fields="id,name,author",
        profile=args.profile,
    )
    print(f"  Found {len(modules)} installed modules", file=sys.stderr)

    print("Fetching module dependencies...", file=sys.stderr)
    deps = _fetch_all_pages(
        model="ir.module.module.dependency",
        domain="[]",
        fields="module_id,name",
        profile=args.profile,
    )
    print(f"  Found {len(deps)} dependency records", file=sys.stderr)

    # Build graph with ALL modules (including native) to preserve dependency
    # connectivity. Native modules are filtered from the OUTPUT, not the graph.
    downstream = _build_graph(modules, deps)
    levels = _compute_levels(modules, downstream)

    if not args.include_native:
        native_names = DEFAULT_NATIVE_NAMES | frozenset(args.extra_native)
        original_count = sum(len(level) for level in levels)
        levels = [[m for m in level if not _is_native(m, native_names)] for level in levels]
        levels = [level for level in levels if level]
        filtered = original_count - sum(len(level) for level in levels)
        print(f"  Filtered {filtered} native modules from output", file=sys.stderr)

    levels = [level for level in levels if level]

    total_modules = sum(len(level) for level in levels)
    print(f"  Computed {len(levels)} dependency levels for {total_modules} modules", file=sys.stderr)

    print(_format_output(levels, args.fmt))


if __name__ == "__main__":
    main()

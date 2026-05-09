#!/usr/bin/env python3
"""Module dependency tree analyzer — CLI entry point.

Fetches installed Odoo modules and their dependencies via odoo-mcp,
builds the dependency graph client-side, and outputs a priority-sorted
report where leaf modules (no dependents) appear first — useful for
planning migration order.

Usage:
    python module_deps.py --profile vauxoo
    python module_deps.py --profile vauxoo --format table
    python module_deps.py --profile vauxoo --include-native
"""

from __future__ import annotations

import sys

import click

from odoo_mcp_multi.operations import op_search_read
from odoo_mcp_multi.skills.module_deps_lib import (
    DEFAULT_NATIVE_NAMES,
    _build_graph,
    _compute_levels,
    _format_output,
    _is_native,
)


def _fetch_all_pages(model: str, domain: str, fields: str, profile: str) -> list[dict]:
    """Paginate through all records, handling the envelope automatically."""
    all_records: list[dict] = []
    offset = 0
    limit = 500
    while True:
        result = op_search_read(
            model=model,
            domain=domain,
            fields=fields,
            limit=limit,
            offset=offset,
            profile=profile,
        )
        if "success" in result and result["success"] is False:
            click.echo(f"Error: {result['error']}", err=True)
            sys.exit(1)
        all_records.extend(result.get("records", []))
        if not result.get("has_more", False):
            break
        offset = result["next_offset"]
    return all_records


@click.command()
@click.option("--profile", "-p", required=True, help="Odoo profile to connect to")
@click.option(
    "--format",
    "-F",
    "fmt",
    default="csv",
    type=click.Choice(["csv", "table", "json"], case_sensitive=False),
    help="Output format (default: csv)",
)
@click.option("--include-native", is_flag=True, default=False, help="Include native Odoo modules in the output")
@click.option(
    "--extra-native",
    multiple=True,
    help="Additional module names to treat as native (repeatable)",
)
def main(profile: str, fmt: str, include_native: bool, extra_native: tuple) -> None:
    """Analyze Odoo module dependency tree for migration planning.

    Outputs a priority-sorted list where Level 1 = base dependencies,
    Level N = modules that depend on Level N-1. Migrate lower levels first.
    """
    click.echo("Fetching installed modules...", err=True)
    modules = _fetch_all_pages(
        model="ir.module.module",
        domain="[('state', '=', 'installed')]",
        fields="id,name,author",
        profile=profile,
    )
    click.echo(f"  Found {len(modules)} installed modules", err=True)

    click.echo("Fetching module dependencies...", err=True)
    deps = _fetch_all_pages(
        model="ir.module.module.dependency",
        domain="[]",
        fields="module_id,name",
        profile=profile,
    )
    click.echo(f"  Found {len(deps)} dependency records", err=True)

    # Build graph with ALL modules (including native) to preserve dependency
    # connectivity. Native modules are filtered from the OUTPUT, not the graph.
    downstream = _build_graph(modules, deps)
    levels = _compute_levels(modules, downstream)

    if not include_native:
        native_names = DEFAULT_NATIVE_NAMES | frozenset(extra_native)
        original_count = sum(len(level) for level in levels)
        levels = [[m for m in level if not _is_native(m, native_names)] for level in levels]
        levels = [level for level in levels if level]
        filtered = original_count - sum(len(level) for level in levels)
        click.echo(f"  Filtered {filtered} native modules from output", err=True)

    levels = [level for level in levels if level]

    total_modules = sum(len(level) for level in levels)
    click.echo(f"  Computed {len(levels)} dependency levels for {total_modules} modules", err=True)

    click.echo(_format_output(levels, fmt))


if __name__ == "__main__":
    main()

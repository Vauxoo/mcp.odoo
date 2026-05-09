"""Module dependency tree analyzer — library functions.

Pure functions for building and analyzing Odoo module dependency graphs.
These are imported by the CLI script and by tests. No I/O or RPC calls
happen in this module — all data is passed in as arguments.
"""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict, deque
from typing import Any

# Modules that are third-party but should be treated as native during
# migration planning. Adjust per project via --extra-native flag.
DEFAULT_NATIVE_NAMES = frozenset(
    {
        "l10n_latam_base",
        "l10n_latam_invoice_document",
        "l10n_mx_reports",
        "l10n_mx_reports_closing",
        "l10n_pe_edi",
        "l10n_pe_reports",
        "sale_subscription",
        "web_environment_ribbon_isolated",
    }
)

# Authors that identify a module as native Odoo.
NATIVE_AUTHORS = {"Odoo S.A.", "Odoo", "Odoo SA"}


def _is_native(module: dict, extra_names: frozenset) -> bool:
    """Determine if a module is native Odoo (should be excluded)."""
    name = module["name"]
    author = module.get("author", "") or ""

    if name in extra_names:
        return True

    # CoA modules: l10n_XX (exactly 2 chars after l10n_)
    if len(name) == 7 and name.startswith("l10n_"):
        return True

    for native_author in NATIVE_AUTHORS:
        if native_author.lower() in author.lower():
            return True

    return False


def _build_graph(modules: list[dict], deps: list[dict]) -> dict[str, set]:
    """Build downstream adjacency lists: dep_name → {modules that depend on it}."""
    installed_names = {m["name"] for m in modules}
    id_to_name: dict[int, str] = {m["id"]: m["name"] for m in modules}

    downstream: dict[str, set] = defaultdict(set)
    for dep in deps:
        # module_id is [id, name] from Odoo, or plain int in some versions
        module_id: Any = dep["module_id"]
        if isinstance(module_id, list):
            module_id = module_id[0]
        parent_name = id_to_name.get(module_id)
        child_name = dep["name"]
        if parent_name and child_name in installed_names:
            # parent_name DEPENDS ON child_name
            # → child_name's downstream includes parent_name
            downstream[child_name].add(parent_name)

    return downstream


def _compute_levels(modules: list[dict], downstream: dict[str, set]) -> list[list[dict]]:
    """BFS from 'base' to compute dependency priority levels.

    Level 0 = base. Level N = modules whose deepest dependency is at level N-1.
    Modules not reachable from base are placed in the last level.
    """
    name_to_module = {m["name"]: m for m in modules}
    installed_names = set(name_to_module.keys())

    depth: dict[str, int] = {}
    queue: deque = deque()

    if "base" in installed_names:
        depth["base"] = 0
        queue.append("base")

    while queue:
        current = queue.popleft()
        current_depth = depth[current]
        for child in downstream.get(current, set()):
            if child not in installed_names:
                continue
            # Longest path from base determines the level — ensures all
            # dependencies of a module are at lower levels.
            if child not in depth or depth[child] < current_depth + 1:
                depth[child] = current_depth + 1
                queue.append(child)

    max_depth = max(depth.values()) if depth else 0
    levels: list[list[dict]] = [[] for _ in range(max_depth + 1)]
    unreachable: list[dict] = []

    for name, mod in sorted(name_to_module.items()):
        if name in depth:
            levels[depth[name]].append(mod)
        else:
            unreachable.append(mod)

    if unreachable:
        levels.append(unreachable)

    return levels


def _format_output(levels: list[list[dict]], fmt: str) -> str:
    """Format the leveled module list in the requested format."""
    if fmt == "json":
        rows = []
        for level_num, mods in enumerate(levels, start=1):
            for m in mods:
                rows.append({"level": level_num, "name": m["name"], "author": m.get("author", "")})
        return json.dumps(rows, indent=2, ensure_ascii=False)

    if fmt == "table":
        lines = ["| Level | Name | Author |", "| --- | --- | --- |"]
        for level_num, mods in enumerate(levels, start=1):
            for m in mods:
                author = (m.get("author", "") or "").replace("|", "\\|")
                lines.append(f"| {level_num} | {m['name']} | {author} |")
        return "\n".join(lines)

    # csv (default)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Level", "Name", "Author"])
    for level_num, mods in enumerate(levels, start=1):
        for m in mods:
            writer.writerow([level_num, m["name"], m.get("author", "")])
    return buf.getvalue().rstrip("\r\n").replace("\r\n", "\n")

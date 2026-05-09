"""Tests for the module dependency tree analyzer.

Tests the pure graph logic (no RPC) — the BFS level computation,
native module filtering, and output formatters.
"""

import json

from odoo_mcp_multi.skills.module_deps_lib import (
    DEFAULT_NATIVE_NAMES,
    _build_graph,
    _compute_levels,
    _format_output,
    _is_native,
)

# ---------------------------------------------------------------------------
# _is_native
# ---------------------------------------------------------------------------


def test_is_native_by_author_odoo_sa():
    assert _is_native({"name": "web", "author": "Odoo S.A."}, frozenset()) is True


def test_is_native_by_author_odoo():
    assert _is_native({"name": "base_setup", "author": "Odoo"}, frozenset()) is True


def test_is_native_by_author_case_insensitive():
    assert _is_native({"name": "mail", "author": "odoo sa"}, frozenset()) is True


def test_is_native_by_l10n_pattern():
    assert _is_native({"name": "l10n_mx", "author": "Vauxoo"}, frozenset()) is True


def test_is_native_l10n_longer_name_not_matched():
    """l10n_mx_reports is NOT matched by the l10n_XX pattern — it needs explicit listing."""
    assert _is_native({"name": "l10n_mx_reports", "author": "Vauxoo"}, frozenset()) is False


def test_is_native_by_extra_names():
    assert _is_native({"name": "my_base", "author": "My Company"}, frozenset({"my_base"})) is True


def test_is_native_default_names():
    assert _is_native({"name": "sale_subscription", "author": "Vauxoo"}, DEFAULT_NATIVE_NAMES) is True


def test_not_native():
    assert _is_native({"name": "vauxoo_custom", "author": "Vauxoo"}, frozenset()) is False


def test_is_native_empty_author():
    assert _is_native({"name": "some_module", "author": ""}, frozenset()) is False


def test_is_native_false_author():
    """Odoo returns False for empty fields."""
    assert _is_native({"name": "some_module", "author": False}, frozenset()) is False


# ---------------------------------------------------------------------------
# _build_graph
# ---------------------------------------------------------------------------

SAMPLE_MODULES = [
    {"id": 1, "name": "base", "author": "Odoo"},
    {"id": 2, "name": "sale", "author": "Odoo"},
    {"id": 3, "name": "crm", "author": "Odoo"},
    {"id": 4, "name": "vauxoo_crm", "author": "Vauxoo"},
]

SAMPLE_DEPS = [
    # sale depends on base
    {"module_id": [2, "sale"], "name": "base"},
    # crm depends on base
    {"module_id": [3, "crm"], "name": "base"},
    # vauxoo_crm depends on crm and sale
    {"module_id": [4, "vauxoo_crm"], "name": "crm"},
    {"module_id": [4, "vauxoo_crm"], "name": "sale"},
]


def test_build_graph_basic():
    downstream = _build_graph(SAMPLE_MODULES, SAMPLE_DEPS)
    # base → {sale, crm} (sale and crm depend on base)
    assert "sale" in downstream["base"]
    assert "crm" in downstream["base"]
    # crm → {vauxoo_crm}
    assert "vauxoo_crm" in downstream["crm"]
    # sale → {vauxoo_crm}
    assert "vauxoo_crm" in downstream["sale"]


def test_build_graph_ignores_uninstalled():
    """Dependencies referencing modules not in the installed list are ignored."""
    modules = [{"id": 1, "name": "base", "author": "Odoo"}]
    deps = [{"module_id": [99, "ghost_module"], "name": "base"}]
    downstream = _build_graph(modules, deps)
    # base has no downstream because ghost_module is not installed
    assert len(downstream.get("base", set())) == 0


def test_build_graph_integer_module_id():
    """Some Odoo versions return module_id as plain int, not [id, name]."""
    modules = [
        {"id": 1, "name": "base", "author": "Odoo"},
        {"id": 2, "name": "sale", "author": "Odoo"},
    ]
    deps = [{"module_id": 2, "name": "base"}]
    downstream = _build_graph(modules, deps)
    assert "sale" in downstream["base"]


# ---------------------------------------------------------------------------
# _compute_levels
# ---------------------------------------------------------------------------


def test_compute_levels_linear():
    downstream = _build_graph(SAMPLE_MODULES, SAMPLE_DEPS)
    levels = _compute_levels(SAMPLE_MODULES, downstream)

    # Level 0: base
    assert any(m["name"] == "base" for m in levels[0])
    # Level 1: sale, crm (depend only on base)
    level1_names = {m["name"] for m in levels[1]}
    assert "sale" in level1_names
    assert "crm" in level1_names
    # Level 2: vauxoo_crm (depends on sale + crm)
    assert any(m["name"] == "vauxoo_crm" for m in levels[2])


def test_compute_levels_single_module():
    modules = [{"id": 1, "name": "base", "author": "Odoo"}]
    downstream = _build_graph(modules, [])
    levels = _compute_levels(modules, downstream)
    assert len(levels) == 1
    assert levels[0][0]["name"] == "base"


def test_compute_levels_unreachable():
    """Modules not connected to base end up in the last level."""
    modules = [
        {"id": 1, "name": "base", "author": "Odoo"},
        {"id": 2, "name": "orphan", "author": "Someone"},
    ]
    downstream = _build_graph(modules, [])
    levels = _compute_levels(modules, downstream)
    # base at level 0, orphan at the last level
    assert levels[0][0]["name"] == "base"
    last_level_names = {m["name"] for m in levels[-1]}
    assert "orphan" in last_level_names


# ---------------------------------------------------------------------------
# _format_output
# ---------------------------------------------------------------------------


def test_format_csv():
    levels = [[{"name": "sale", "author": "Odoo"}], [{"name": "vauxoo_crm", "author": "Vauxoo"}]]
    output = _format_output(levels, "csv")
    lines = output.split("\n")
    assert lines[0] == "Level,Name,Author"
    assert lines[1] == "1,sale,Odoo"
    assert lines[2] == "2,vauxoo_crm,Vauxoo"


def test_format_table():
    levels = [[{"name": "sale", "author": "Odoo"}]]
    output = _format_output(levels, "table")
    assert "| Level | Name | Author |" in output
    assert "| 1 | sale | Odoo |" in output


def test_format_json():
    levels = [[{"name": "sale", "author": "Odoo"}]]
    output = _format_output(levels, "json")
    data = json.loads(output)
    assert data[0]["level"] == 1
    assert data[0]["name"] == "sale"


def test_format_csv_author_with_comma():
    """Authors containing commas are properly quoted in CSV."""
    levels = [[{"name": "mod", "author": "Company A, Inc."}]]
    output = _format_output(levels, "csv")
    assert '"Company A, Inc."' in output


def test_format_empty_levels():
    output = _format_output([], "csv")
    assert output == "Level,Name,Author"

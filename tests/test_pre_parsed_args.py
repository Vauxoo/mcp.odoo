"""Test that parse functions handle pre-deserialized arguments.

Some MCP clients (e.g. Claude Code) deserialize JSON arguments into native
Python objects before delivering them to the tool handler, even when the
parameter schema declares ``type: "string"``.  These tests verify that the
parse helpers work regardless of whether the input is a raw JSON string or
an already-parsed Python object.
"""

from odoo_mcp_multi.utils import parse_domain, parse_ids, parse_json_arg


class TestParseDomainPreParsed:
    def test_string_input(self):
        assert parse_domain("[('name', '=', 'test')]") == [("name", "=", "test")]

    def test_list_input(self):
        domain = [("name", "=", "test")]
        assert parse_domain(domain) == domain

    def test_empty_string(self):
        assert parse_domain("[]") == []

    def test_empty_list(self):
        assert parse_domain([]) == []


class TestParseIdsPreParsed:
    def test_string_input(self):
        assert parse_ids("[1, 2, 3]") == [1, 2, 3]

    def test_list_input(self):
        assert parse_ids([1, 2, 3]) == [1, 2, 3]

    def test_int_input(self):
        assert parse_ids(42) == [42]

    def test_csv_string(self):
        assert parse_ids("1,2,3") == [1, 2, 3]

    def test_empty_string(self):
        assert parse_ids("") == []

    def test_empty_list(self):
        assert parse_ids([]) == []


class TestParseJsonArgPreParsed:
    def test_string_dict(self):
        result = parse_json_arg('{"name": "John"}', {})
        assert result == {"name": "John"}

    def test_dict_input(self):
        data = {"name": "John", "age": 30}
        assert parse_json_arg(data, {}) == data

    def test_string_list(self):
        result = parse_json_arg("[[1, 2]]", [])
        assert result == [[1, 2]]

    def test_list_input(self):
        data = [[1, 2]]
        assert parse_json_arg(data, []) == data

    def test_int_input(self):
        assert parse_json_arg(42, None) == 42

    def test_bool_input(self):
        assert parse_json_arg(True, None) is True

    def test_empty_string(self):
        assert parse_json_arg("", {"default": True}) == {"default": True}

    def test_empty_dict_string(self):
        assert parse_json_arg("{}", {"default": True}) == {"default": True}

    def test_none_input(self):
        assert parse_json_arg(None, []) == []

    def test_nested_dict(self):
        """Simulate the exact failing case: create() with values as dict."""
        data = {"task_id": 96492, "project_id": 403, "name": "Test", "unit_amount": 1.0}
        assert parse_json_arg(data, {}) == data

    def test_nested_list_of_dicts(self):
        """Simulate the exact failing case: execute_kw() with args as list."""
        data = [[{"task_id": 96492, "name": "Test"}]]
        assert parse_json_arg(data, []) == data

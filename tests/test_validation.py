"""Tests for utils/validation.py — schema and widget validation utilities."""

import unittest
from typing import ClassVar
from unittest import mock

from utils.validation import (
    _format_allowed_values,
    _format_config_value,
    _get_config_collection,
    _get_named_format_keys,
    _has_named_custom_widget,
    _resolve_schema_ref,
    _schema_type_matches,
    _validate_indexed_reference,
    _validate_schema_enums,
    validate_format_strings,
    validate_widget_reference,
    validate_widgets,
)


class ResolveSchemaRefTest(unittest.TestCase):
    """Test _resolve_schema_ref with local JSON schema references."""

    def test_resolves_local_ref(self):
        root = {"definitions": {"Foo": {"type": "string"}}}
        node = {"$ref": "#/definitions/Foo"}
        self.assertEqual(_resolve_schema_ref(node, root), {"type": "string"})

    def test_no_ref_returns_node_unchanged(self):
        node = {"type": "integer"}
        self.assertIs(_resolve_schema_ref(node, {}), node)

    def test_non_string_ref_returns_node(self):
        node = {"$ref": 42}
        self.assertIs(_resolve_schema_ref(node, {}), node)

    def test_external_ref_not_resolved(self):
        node = {"$ref": "http://example.com/schema.json"}
        self.assertIs(_resolve_schema_ref(node, {}), node)

    def test_broken_ref_returns_node(self):
        node = {"$ref": "#/missing/path"}
        self.assertIs(_resolve_schema_ref(node, {"other": 1}), node)

    def test_chained_refs(self):
        root = {"a": {"$ref": "#/b"}, "b": {"type": "boolean"}}
        node = {"$ref": "#/a"}
        self.assertEqual(_resolve_schema_ref(node, root), {"type": "boolean"})


class SchemaTypeMatchesTest(unittest.TestCase):
    """Test _schema_type_matches type comparison logic."""

    def test_none_schema_accepts_any(self):
        self.assertTrue(_schema_type_matches("anything", None))

    def test_string_matches_string(self):
        self.assertTrue(_schema_type_matches("hello", "string"))

    def test_int_matches_integer(self):
        self.assertTrue(_schema_type_matches(42, "integer"))

    def test_int_matches_number(self):
        self.assertTrue(_schema_type_matches(42, "number"))

    def test_float_matches_number(self):
        self.assertTrue(_schema_type_matches(3.14, "number"))

    def test_float_does_not_match_integer(self):
        self.assertFalse(_schema_type_matches(3.14, "integer"))

    def test_bool_matches_boolean(self):
        self.assertTrue(_schema_type_matches(True, "boolean"))

    def test_bool_does_not_match_string(self):
        self.assertFalse(_schema_type_matches(True, "string"))

    def test_none_matches_null(self):
        self.assertTrue(_schema_type_matches(None, "null"))

    def test_dict_matches_object(self):
        self.assertTrue(_schema_type_matches({"a": 1}, "object"))

    def test_list_matches_array(self):
        self.assertTrue(_schema_type_matches([1, 2], "array"))

    def test_union_type(self):
        self.assertTrue(_schema_type_matches("hi", ["string", "null"]))
        self.assertTrue(_schema_type_matches(None, ["string", "null"]))
        self.assertFalse(_schema_type_matches(42, ["string", "null"]))


class FormattingHelpersTest(unittest.TestCase):
    """Test _format_config_value and _format_allowed_values helpers."""

    def test_format_config_value_contains_repr(self):
        result = _format_config_value("bad")
        self.assertIn("'bad'", result)

    def test_format_allowed_values_lists_items(self):
        result = _format_allowed_values(["a", "b"])
        self.assertIn("'a'", result)
        self.assertIn("'b'", result)


class ValidateSchemaEnumsTest(unittest.TestCase):
    """Test _validate_schema_enums with enum, pattern, anyOf, oneOf, nesting."""

    def test_no_schema_dict_passes(self):
        _validate_schema_enums("val", "not-a-dict", {}, "p")

    def test_enum_valid(self):
        schema = {"type": "string", "enum": ["a", "b"]}
        _validate_schema_enums("a", schema, schema, "p")

    def test_enum_invalid(self):
        schema = {"type": "string", "enum": ["a", "b"]}
        with self.assertRaises(ValueError):
            _validate_schema_enums("c", schema, schema, "p")

    def test_pattern_valid(self):
        schema = {"type": "string", "pattern": "^\\d{4}$"}
        _validate_schema_enums("2024", schema, schema, "p")

    def test_pattern_invalid(self):
        schema = {"type": "string", "pattern": "^\\d{4}$"}
        with self.assertRaises(ValueError):
            _validate_schema_enums("abc", schema, schema, "p")

    def test_any_of_first_match_passes(self):
        schema = {
            "anyOf": [
                {"type": "string", "enum": ["x"]},
                {"type": "string", "enum": ["y"]},
            ]
        }
        _validate_schema_enums("x", schema, schema, "p")
        _validate_schema_enums("y", schema, schema, "p")

    def test_any_of_no_match_raises(self):
        schema = {
            "anyOf": [
                {"type": "string", "enum": ["x"]},
                {"type": "string", "enum": ["y"]},
            ]
        }
        with self.assertRaises(ValueError):
            _validate_schema_enums("z", schema, schema, "p")

    def test_one_of_exact_match(self):
        schema = {
            "oneOf": [
                {"type": "string", "enum": ["a"]},
                {"type": "string", "enum": ["b"]},
            ]
        }
        _validate_schema_enums("a", schema, schema, "p")

    def test_one_of_no_match_raises(self):
        schema = {
            "oneOf": [
                {"type": "string", "enum": ["a"]},
                {"type": "string", "enum": ["b"]},
            ]
        }
        with self.assertRaises(ValueError):
            _validate_schema_enums("c", schema, schema, "p")

    def test_type_mismatch_skips_enum_check(self):
        schema = {"type": "string", "enum": ["a"]}
        _validate_schema_enums(42, schema, schema, "p")

    def test_nested_object_validates_children(self):
        schema = {
            "type": "object",
            "properties": {"color": {"type": "string", "enum": ["red", "blue"]}},
        }
        _validate_schema_enums({"color": "red"}, schema, schema, "p")

    def test_nested_object_child_invalid(self):
        schema = {
            "type": "object",
            "properties": {"color": {"type": "string", "enum": ["red", "blue"]}},
        }
        with self.assertRaises(ValueError):
            _validate_schema_enums({"color": "green"}, schema, schema, "p")

    def test_array_items_validated(self):
        schema = {
            "type": "array",
            "items": {"type": "string", "enum": ["x", "y"]},
        }
        _validate_schema_enums(["x", "y"], schema, schema, "p")

    def test_array_items_invalid(self):
        schema = {
            "type": "array",
            "items": {"type": "string", "enum": ["x", "y"]},
        }
        with self.assertRaises(ValueError):
            _validate_schema_enums(["x", "z"], schema, schema, "p")

    def test_tuple_items_validated(self):
        schema = {
            "type": "array",
            "items": [
                {"type": "string", "enum": ["a"]},
                {"type": "integer"},
            ],
        }
        _validate_schema_enums(["a", 1], schema, schema, "p")

    def test_tuple_items_out_of_range_ignored(self):
        schema = {
            "type": "array",
            "items": [{"type": "string", "enum": ["a"]}],
        }
        _validate_schema_enums(["a", "extra"], schema, schema, "p")

    def test_additional_properties_validated(self):
        schema = {
            "type": "object",
            "properties": {"known": {"type": "string"}},
            "additionalProperties": {"type": "integer"},
        }
        _validate_schema_enums({"known": "ok", "extra": 5}, schema, schema, "p")

    def test_additional_properties_invalid_enum(self):
        schema = {
            "type": "object",
            "properties": {"known": {"type": "string"}},
            "additionalProperties": {
                "type": "string",
                "enum": ["a", "b"],
            },
        }
        with self.assertRaises(ValueError):
            _validate_schema_enums({"known": "ok", "extra": "c"}, schema, schema, "p")

    def test_ref_is_resolved(self):
        root = {
            "defs": {"Color": {"type": "string", "enum": ["r", "g", "b"]}},
        }
        schema = {"$ref": "#/defs/Color"}
        _validate_schema_enums("r", schema, root, "p")
        with self.assertRaises(ValueError):
            _validate_schema_enums("x", schema, root, "p")


class GetConfigCollectionTest(unittest.TestCase):
    """Test _get_config_collection dispatcher for different widget types."""

    def test_custom_button(self):
        data = {"widgets": {"custom_button_group": {"buttons": [{"id": "b1"}]}}}
        result = _get_config_collection(data, "custom_button")
        self.assertEqual(result, [{"id": "b1"}])

    def test_group(self):
        data = {"widget_groups": [{"id": "g1"}]}
        self.assertEqual(_get_config_collection(data, "group"), [{"id": "g1"}])

    def test_collapsible(self):
        data = {"collapsible_groups": [{"id": "c1"}]}
        result = _get_config_collection(data, "collapsible")
        self.assertEqual(result, [{"id": "c1"}])

    def test_custom_widget(self):
        data = {"widgets": {"custom_widget": [{"id": "w1"}]}}
        result = _get_config_collection(data, "custom_widget")
        self.assertEqual(result, [{"id": "w1"}])

    def test_unknown_type_returns_empty(self):
        self.assertEqual(_get_config_collection({}, "unknown"), [])


class ValidateIndexedReferenceTest(unittest.TestCase):
    """Test _validate_indexed_reference with numeric and string IDs."""

    def test_valid_numeric_index(self):
        collection = ["a", "b", "c"]
        result = _validate_indexed_reference("1", collection, "widget group", "layout")
        self.assertEqual(result, 1)

    def test_out_of_range_index(self):
        collection = ["a", "b"]
        with self.assertRaisesRegex(ValueError, "out of range"):
            _validate_indexed_reference("5", collection, "widget group", "layout")

    def test_non_list_collection(self):
        with self.assertRaisesRegex(ValueError, "must be an array"):
            _validate_indexed_reference("0", "not-a-list", "widget group", "layout")

    def test_string_id_collapsible_group(self):
        collection = [{"id": "tools"}, {"id": "utils"}]
        result = _validate_indexed_reference(
            "tools", collection, "collapsible group", "layout"
        )
        self.assertEqual(result, 0)

    def test_string_id_widget_group(self):
        collection = [{"id": "work"}]
        result = _validate_indexed_reference(
            "work", collection, "widget group", "layout"
        )
        self.assertEqual(result, 0)

    def test_string_id_not_found(self):
        collection = [{"id": "a"}]
        with self.assertRaisesRegex(ValueError, "No.*with id.*found"):
            _validate_indexed_reference(
                "missing", collection, "collapsible group", "layout"
            )

    def test_string_id_unsupported_type(self):
        with self.assertRaisesRegex(ValueError, "Must be a number"):
            _validate_indexed_reference("abc", ["x"], "other type", "layout")


class HasNamedCustomWidgetTest(unittest.TestCase):
    """Test _has_named_custom_widget detection across config shapes."""

    def test_not_custom_prefix(self):
        self.assertFalse(_has_named_custom_widget("battery", {}))

    def test_shape1_direct_dict(self):
        data = {"widgets": {"custom/hello": {"exec": "echo hi"}}}
        self.assertTrue(_has_named_custom_widget("custom/hello", data))

    def test_shape1_missing(self):
        data = {"widgets": {}}
        self.assertFalse(_has_named_custom_widget("custom/hello", data))

    def test_shape2_custom_widget_dict(self):
        data = {"widgets": {"custom_widget": {"hello": {"exec": "echo"}}}}
        self.assertTrue(_has_named_custom_widget("custom/hello", data))

    def test_shape3_custom_widget_list(self):
        data = {"widgets": {"custom_widget": [{"name": "hello"}]}}
        self.assertTrue(_has_named_custom_widget("custom/hello", data))

    def test_shape3_no_match(self):
        data = {"widgets": {"custom_widget": [{"name": "other"}]}}
        self.assertFalse(_has_named_custom_widget("custom/hello", data))

    def test_widgets_not_dict(self):
        data = {"widgets": "bad"}
        self.assertFalse(_has_named_custom_widget("custom/x", data))


class ValidateWidgetReferenceTest(unittest.TestCase):
    """Test validate_widget_reference dispatcher for regular and special refs."""

    DEFAULT: ClassVar[dict] = {"widgets": {"battery": {}, "volume": {}}}

    def test_valid_regular_widget(self):
        validate_widget_reference("battery", {}, self.DEFAULT, "layout")

    def test_invalid_regular_widget(self):
        with self.assertRaisesRegex(ValueError, "Invalid widget"):
            validate_widget_reference("nonexistent", {}, self.DEFAULT, "layout")

    def test_valid_special_numeric(self):
        data = {"widget_groups": [{"widgets": []}]}
        validate_widget_reference("@group:0", data, self.DEFAULT, "layout")

    def test_valid_special_string_id(self):
        data = {"widget_groups": [{"id": "main", "widgets": []}]}
        validate_widget_reference("@group:main", data, self.DEFAULT, "layout")

    def test_invalid_special_type(self):
        with self.assertRaisesRegex(ValueError, "Unknown widget type"):
            validate_widget_reference("@bogus:0", {}, self.DEFAULT, "layout")

    def test_invalid_reference_format(self):
        with self.assertRaisesRegex(ValueError, "Invalid reference format"):
            validate_widget_reference("@no_colon", {}, self.DEFAULT, "layout")

    def test_named_custom_widget_valid(self):
        data = {"widgets": {"custom/myapp": {"exec": "echo"}}}
        validate_widget_reference("custom/myapp", data, self.DEFAULT, "layout")


class GetNamedFormatKeysTest(unittest.TestCase):
    """Test _get_named_format_keys extraction from format strings."""

    def test_simple_keys(self):
        result = _get_named_format_keys("{title} - {artist}")
        self.assertEqual(result, {"title", "artist"})

    def test_no_keys(self):
        self.assertEqual(_get_named_format_keys("no keys here"), set())

    def test_repeated_key(self):
        self.assertEqual(_get_named_format_keys("{x}{x}"), {"x"})


class ValidateFormatStringsTest(unittest.TestCase):
    """Test validate_format_strings for widget label format validation."""

    def test_valid_format_no_warning(self):
        validate_format_strings(
            {"widgets": {"mpris": {"label_format": "{title} - {artist}"}}}
        )

    @mock.patch("utils.validation.logger")
    def test_unknown_key_warns(self, mock_logger):
        validate_format_strings(
            {"widgets": {"mpris": {"label_format": "{unknown_key}"}}}
        )
        mock_logger.warning.assert_called()
        msg = mock_logger.warning.call_args[0][0]
        self.assertIn("unknown key", msg)

    def test_non_string_format_ignored(self):
        validate_format_strings({"widgets": {"mpris": {"label_format": 42}}})

    @mock.patch("utils.validation.logger")
    def test_invalid_format_string_warns(self, mock_logger):
        validate_format_strings({"widgets": {"mpris": {"label_format": "{unclosed"}}})
        mock_logger.warning.assert_called()
        msg = mock_logger.warning.call_args[0][0]
        self.assertIn("invalid format", msg)


class ValidateWidgetsTest(unittest.TestCase):
    """Test validate_widgets integration with layout and group validation."""

    DEFAULT: ClassVar[dict] = {"widgets": {"battery": {}, "volume": {}}}

    def test_valid_layout(self):
        parsed = {"layout": {"left_section": ["battery"], "right_section": []}}
        validate_widgets(parsed, self.DEFAULT)

    def test_invalid_widget_in_layout(self):
        parsed = {"layout": {"left_section": ["nonexistent"]}}
        with self.assertRaises(ValueError):
            validate_widgets(parsed, self.DEFAULT)

    def test_valid_group_widgets(self):
        parsed = {
            "layout": {},
            "widget_groups": [{"widgets": ["battery"]}],
        }
        validate_widgets(parsed, self.DEFAULT)

    def test_invalid_group_widget(self):
        parsed = {
            "layout": {},
            "widget_groups": [{"widgets": ["nonexistent"]}],
        }
        with self.assertRaises(ValueError):
            validate_widgets(parsed, self.DEFAULT)


if __name__ == "__main__":
    unittest.main()

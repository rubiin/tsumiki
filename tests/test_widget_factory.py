"""Tests for utils/widget_factory.py — widget factory and resolver."""

import unittest
from unittest import mock

from utils.widget_factory import IndexedWidgetHelper, WidgetResolver


class IndexedWidgetHelperValidateAndGetIndexTest(unittest.TestCase):
    """Test validate_and_get_index with numeric and string identifiers."""

    def test_valid_numeric_index(self):
        result = IndexedWidgetHelper.validate_and_get_index("0", ["a", "b"], "group")
        self.assertEqual(result, 0)

    def test_valid_numeric_index_last(self):
        result = IndexedWidgetHelper.validate_and_get_index(
            "2", ["a", "b", "c"], "group"
        )
        self.assertEqual(result, 2)

    def test_out_of_range_returns_none(self):
        result = IndexedWidgetHelper.validate_and_get_index("5", ["a", "b"], "group")
        self.assertIsNone(result)

    def test_non_list_collection_returns_none(self):
        result = IndexedWidgetHelper.validate_and_get_index("0", "not-a-list", "group")
        self.assertIsNone(result)

    def test_string_id_finds_match(self):
        collection = [{"id": "tools"}, {"id": "utils"}]
        result = IndexedWidgetHelper.validate_and_get_index(
            "tools", collection, "collapsible"
        )
        self.assertEqual(result, 0)

    def test_string_id_second_item(self):
        collection = [{"id": "tools"}, {"id": "utils"}]
        result = IndexedWidgetHelper.validate_and_get_index(
            "utils", collection, "collapsible"
        )
        self.assertEqual(result, 1)

    def test_string_id_no_match_returns_none(self):
        collection = [{"id": "tools"}]
        result = IndexedWidgetHelper.validate_and_get_index(
            "missing", collection, "collapsible"
        )
        self.assertIsNone(result)

    def test_string_id_non_dict_items_skipped(self):
        collection = ["not-a-dict", {"id": "found"}]
        result = IndexedWidgetHelper.validate_and_get_index(
            "found", collection, "group"
        )
        self.assertEqual(result, 1)


class IndexedWidgetHelperGetConfigPathTest(unittest.TestCase):
    """Test get_config_path safe navigation."""

    def test_simple_path(self):
        config = {"a": {"b": [1, 2, 3]}}
        result = IndexedWidgetHelper.get_config_path(config, "a", "b")
        self.assertEqual(result, [1, 2, 3])

    def test_missing_path_returns_empty(self):
        config = {"a": {}}
        result = IndexedWidgetHelper.get_config_path(config, "a", "missing")
        self.assertEqual(result, [])

    def test_non_list_value_returns_empty(self):
        config = {"a": {"b": "not-a-list"}}
        result = IndexedWidgetHelper.get_config_path(config, "a", "b")
        self.assertEqual(result, [])

    def test_deep_path(self):
        config = {"a": {"b": {"c": [10]}}}
        result = IndexedWidgetHelper.get_config_path(config, "a", "b", "c")
        self.assertEqual(result, [10])


class WidgetResolverParseReferenceTest(unittest.TestCase):
    """Test _parse_reference for @type:identifier parsing."""

    def setUp(self):
        self.resolver = WidgetResolver({})

    def test_simple_reference(self):
        t, id_ = self.resolver._parse_reference("@group:0")
        self.assertEqual(t, "group")
        self.assertEqual(id_, "0")

    def test_string_id(self):
        t, id_ = self.resolver._parse_reference("@collapsible:tools")
        self.assertEqual(t, "collapsible")
        self.assertEqual(id_, "tools")

    def test_no_identifier(self):
        t, id_ = self.resolver._parse_reference("@group")
        self.assertEqual(t, "group")
        self.assertEqual(id_, "")

    def test_colon_in_identifier(self):
        t, id_ = self.resolver._parse_reference("@custom:ns/name")
        self.assertEqual(t, "custom")
        self.assertEqual(id_, "ns/name")


class WidgetResolverResolveWidgetTest(unittest.TestCase):
    """Test resolve_widget dispatching for different widget specs."""

    def setUp(self):
        self.mock_widget_class = mock.Mock(return_value=mock.Mock())
        self.widgets_list = {"battery": self.mock_widget_class}
        self.resolver = WidgetResolver(self.widgets_list)

    def test_simple_widget(self):
        result = self.resolver.resolve_widget("battery", {})
        self.mock_widget_class.assert_called_once()
        self.assertIsNotNone(result)

    def test_unknown_widget_returns_none(self):
        result = self.resolver.resolve_widget("nonexistent", {})
        self.assertIsNone(result)

    def test_reference_without_colon_returns_none(self):
        result = self.resolver.resolve_widget("@group", {})
        self.assertIsNone(result)

    def test_unknown_type_returns_none(self):
        result = self.resolver.resolve_widget("@bogus:0", {})
        self.assertIsNone(result)

    def test_exception_returns_none(self):
        self.mock_widget_class.side_effect = RuntimeError("boom")
        result = self.resolver.resolve_widget("battery", {})
        self.assertIsNone(result)


class WidgetResolverCreateNamedCustomWidgetTest(unittest.TestCase):
    """Test _get_named_custom_widget_config with different config shapes."""

    def setUp(self):
        self.resolver = WidgetResolver({})

    def test_shape1_direct(self):
        config = {"widgets": {"custom/hello": {"exec": "echo"}}}
        result = self.resolver._get_named_custom_widget_config(config, "custom/hello")
        self.assertEqual(result, {"exec": "echo"})

    def test_shape2_dict(self):
        config = {"widgets": {"custom_widget": {"hello": {"exec": "echo"}}}}
        result = self.resolver._get_named_custom_widget_config(config, "custom/hello")
        self.assertEqual(result, {"exec": "echo"})

    def test_shape3_list(self):
        config = {"widgets": {"custom_widget": [{"name": "hello", "exec": "e"}]}}
        result = self.resolver._get_named_custom_widget_config(config, "custom/hello")
        self.assertEqual(result["name"], "hello")

    def test_not_found(self):
        config = {"widgets": {}}
        result = self.resolver._get_named_custom_widget_config(config, "custom/missing")
        self.assertIsNone(result)

    def test_widgets_not_dict(self):
        result = self.resolver._get_named_custom_widget_config(
            {"widgets": "bad"}, "custom/x"
        )
        self.assertIsNone(result)


class WidgetResolverBatchResolveTest(unittest.TestCase):
    """Test batch_resolve filtering and collecting results."""

    def setUp(self):
        mock_cls = mock.Mock(return_value=mock.Mock())
        self.resolver = WidgetResolver({"battery": mock_cls})

    def test_batch_filters_none(self):
        result = self.resolver.batch_resolve(["battery", "nonexistent"], {})
        self.assertEqual(len(result), 1)

    def test_batch_empty(self):
        result = self.resolver.batch_resolve([], {})
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()

"""Tests for the remembered-value helper shared by poll handlers."""

import unittest
from unittest import mock

from utils.change_cache import ChangeCache


class ChangeCacheTest(unittest.TestCase):
    """A poll tick must not re-apply state that did not change."""

    def test_first_call_always_applies(self):
        cache = ChangeCache()
        setter = mock.Mock()

        self.assertTrue(cache.apply("label", "on", setter))
        setter.assert_called_once_with("on")

    def test_unchanged_value_skips_the_setter(self):
        cache = ChangeCache()
        setter = mock.Mock()
        cache.apply("label", "on", setter)

        for _ in range(10):
            self.assertFalse(cache.apply("label", "on", setter))

        setter.assert_called_once_with("on")

    def test_changed_value_applies_again(self):
        cache = ChangeCache()
        setter = mock.Mock()
        cache.apply("label", "on", setter)

        self.assertTrue(cache.apply("label", "off", setter))

        setter.assert_called_with("off")
        self.assertEqual(2, setter.call_count)

    def test_keys_are_tracked_separately(self):
        cache = ChangeCache()
        icon, label = mock.Mock(), mock.Mock()

        cache.apply("icon", "a", icon)
        cache.apply("label", "a", label)

        self.assertFalse(cache.apply("icon", "a", icon))
        self.assertFalse(cache.apply("label", "a", label))

    def test_falsy_values_are_not_confused_with_absence(self):
        cache = ChangeCache()
        setter = mock.Mock()

        cache.apply("active", True, setter)
        self.assertTrue(cache.apply("active", False, setter))
        self.assertTrue(cache.apply("active", True, setter))

        self.assertEqual(3, setter.call_count)


if __name__ == "__main__":
    unittest.main()

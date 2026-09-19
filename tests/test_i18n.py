"""Tests for utils/i18n.py — internationalization support."""

import json
import os
import tempfile
import unittest
from unittest import mock

from utils.i18n import DEFAULT_LANGUAGE, I18n, _, get_i18n


class I18nFlattenDictTest(unittest.TestCase):
    """Test the internal _flatten_dict helper."""

    def setUp(self):
        self.i18n = I18n()

    def test_flat_dict_unchanged(self):
        d = {"a": "1", "b": "2"}
        self.assertEqual(self.i18n._flatten_dict(d), {"a": "1", "b": "2"})

    def test_nested_dict_flattened(self):
        d = {"ui": {"ok": "OK", "cancel": "Cancel"}}
        self.assertEqual(
            self.i18n._flatten_dict(d),
            {"ui.ok": "OK", "ui.cancel": "Cancel"},
        )

    def test_deeply_nested(self):
        d = {"a": {"b": {"c": "val"}}}
        self.assertEqual(self.i18n._flatten_dict(d), {"a.b.c": "val"})

    def test_non_string_values_stringified(self):
        d = {"count": 42}
        self.assertEqual(self.i18n._flatten_dict(d), {"count": "42"})

    def test_empty_dict(self):
        self.assertEqual(self.i18n._flatten_dict({}), {})


class I18nSingletonTest(unittest.TestCase):
    """Test that I18n behaves as a singleton."""

    def test_same_instance(self):
        a = I18n()
        b = I18n()
        self.assertIs(a, b)

    def test_get_i18n_returns_singleton(self):
        a = get_i18n()
        b = get_i18n()
        self.assertIs(a, b)


class I18nTranslateTest(unittest.TestCase):
    """Test the translate method with mocked language files."""

    def setUp(self):
        self.i18n = I18n()
        # Reset internal state for isolation
        self.i18n._translations = {}
        self.i18n._fallback = {}
        self.i18n._language = DEFAULT_LANGUAGE

    def test_translate_returns_key_when_empty(self):
        self.assertEqual(self.i18n.translate("missing.key"), "missing.key")

    def test_translate_from_translations(self):
        self.i18n._translations = {"hello": "Hola"}
        self.assertEqual(self.i18n.translate("hello"), "Hola")

    def test_translate_fallback_to_english(self):
        self.i18n._translations = {}
        self.i18n._fallback = {"hello": "Hello"}
        self.assertEqual(self.i18n.translate("hello"), "Hello")

    def test_translations_take_precedence_over_fallback(self):
        self.i18n._translations = {"hello": "Hola"}
        self.i18n._fallback = {"hello": "Hello"}
        self.assertEqual(self.i18n.translate("hello"), "Hola")

    def test_translate_with_kwargs(self):
        self.i18n._translations = {"greeting": "Hi {name}"}
        self.assertEqual(self.i18n.translate("greeting", name="Bob"), "Hi Bob")

    def test_translate_kwargs_missing_key_returns_text(self):
        self.i18n._translations = {"greeting": "Hi {name}"}
        # Missing kwarg — format fails, returns raw text
        self.assertEqual(self.i18n.translate("greeting"), "Hi {name}")

    def test_language_property(self):
        self.i18n._language = "fr"
        self.assertEqual(self.i18n.language, "fr")


class I18nLoadTest(unittest.TestCase):
    """Test the load method with real temp files."""

    def setUp(self):
        self.i18n = I18n()
        self.i18n._translations = {}
        self.i18n._fallback = {}
        self.i18n._language = DEFAULT_LANGUAGE

    def test_load_existing_language(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lang_file = os.path.join(tmpdir, "fr.json")
            with open(lang_file, "w") as f:
                json.dump({"ui": {"ok": "D'accord"}}, f)

            with (
                mock.patch("utils.i18n.os.path.join", return_value=lang_file),
                mock.patch("utils.i18n.os.path.exists", return_value=True),
                mock.patch(
                    "utils.constants.ASSETS_DIR",
                    tmpdir,
                    create=True,
                ),
            ):
                self.i18n.load("fr")

            self.assertEqual(self.i18n.language, "fr")
            self.assertEqual(self.i18n.translate("ui.ok"), "D'accord")

    def test_load_missing_file(self):
        with (
            mock.patch("utils.i18n.os.path.exists", return_value=False),
            mock.patch("utils.constants.ASSETS_DIR", "/tmp", create=True),
        ):
            self.i18n.load("zz_nonexistent")
        self.assertEqual(self.i18n._translations, {})


class ConvenienceFunctionTest(unittest.TestCase):
    """Test the module-level _() convenience function."""

    def test_returns_translated_string(self):
        i18n = get_i18n()
        i18n._translations = {"test.key": "Test Value"}
        self.assertEqual(_("test.key"), "Test Value")

    def test_returns_key_when_missing(self):
        i18n = get_i18n()
        i18n._translations = {}
        i18n._fallback = {}
        self.assertEqual(_("no.such.key"), "no.such.key")


if __name__ == "__main__":
    unittest.main()

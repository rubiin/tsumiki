"""Tests that ``tsumiki.schema.json`` still describes the config surface.

The schema is hand-edited, and a botched edit once dropped the whole
``widgets.quick_settings`` object while leaving its properties behind inside
``widgets.network_usage`` (``394e6980``). Nothing failed: the file stayed valid
JSON and every config key still resolved, so only ``config.toml`` users lost
autocompletion for the section.
"""

import json
import unittest
from pathlib import Path
from typing import ClassVar

from utils.widget_settings import Modules, Widgets

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "tsumiki.schema.json"

# Every keyword this schema is allowed to use. Anything else inside a property
# definition is a typo, e.g. ``"location": "string"`` written where ``"type"``
# belonged, which silently leaves the key unvalidated.
KNOWN_KEYWORDS = {
    "$schema",
    "$ref",
    "title",
    "type",
    "properties",
    "patternProperties",
    "additionalProperties",
    "items",
    "required",
    "enum",
    "const",
    "default",
    "description",
    "examples",
    "anyOf",
    "oneOf",
    "allOf",
    "not",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minProperties",
    "maxProperties",
}


def _load() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _load_with_duplicates() -> dict:
    def hook(pairs: list[tuple[str, object]]) -> dict:
        seen: set[str] = set()
        for key, _ in pairs:
            if key in seen:
                raise AssertionError(f"duplicate key {key!r} in one schema object")
            seen.add(key)
        return dict(pairs)

    with open(SCHEMA_PATH, encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=hook)


def _declared(block: dict) -> set:
    return set(getattr(block, "__annotations__", {}))


def _property_names(block: dict) -> set:
    return set(block.get("properties", {}))


class TypedDictCoverageMixin:
    """One direction of the drift, shared by the widget and module sections."""

    schema_group = ""
    typed_dicts: ClassVar[dict] = {}

    def _schema(self) -> dict:
        return _load()["properties"][self.schema_group]["properties"]

    def test_every_typed_dict_entry_has_a_schema_object(self):
        missing = set(self.typed_dicts) - set(self._schema())

        self.assertEqual(set(), missing)

    def test_no_schema_entry_is_missing_from_the_typed_dicts(self):
        extra = set(self._schema()) - set(self.typed_dicts)

        self.assertEqual(set(), extra)

    def test_every_typed_dict_declares_exactly_its_schema_keys(self):
        """The TypedDicts are the config's type reference, so they must track it.

        ``BaseConfig`` used to vend a ``label`` toggle that no code read, which
        left ~30 widgets declaring a key the schema and runtime had dropped.
        """
        schema = self._schema()
        drift = {
            name: {
                "typeddict_only": sorted(_declared(td) - _property_names(schema[name])),
                "schema_only": sorted(_property_names(schema[name]) - _declared(td)),
            }
            for name, td in self.typed_dicts.items()
            if _declared(td) != _property_names(schema[name])
        }

        self.assertEqual({}, drift)

    def test_every_required_key_is_also_declared(self):
        """``required`` on an undeclared key validates and autocompletes nothing."""
        undeclared = [
            f"{self.schema_group}.{name}.{key}"
            for name, block in self._schema().items()
            for key in block.get("required", [])
            if key not in block.get("properties", {})
        ]

        self.assertEqual([], undeclared)

    def test_no_declared_property_has_an_empty_schema(self):
        """``"key": {}`` accepts any value and documents nothing.

        The regression: ``394e6980`` left ``interval`` as ``{}`` in three
        widgets, dropping its type and default.
        """
        empty = [
            f"{self.schema_group}.{name}.{key}"
            for name, block in self._schema().items()
            for key, definition in block.get("properties", {}).items()
            if not definition
        ]

        self.assertEqual([], empty)

    def test_no_property_definition_uses_an_unknown_keyword(self):
        """A stray ``"location": "string"`` where ``"type"`` belonged.

        That typo shipped once: ``modules.bar.location`` had no ``type``, so the
        key validated nothing and autocompleted nothing.
        """
        suspect = []

        def walk(node, path: str) -> None:
            if not isinstance(node, dict):
                return
            unknown = sorted(set(node) - KNOWN_KEYWORDS)
            if unknown:
                suspect.append(f"{path}: {unknown}")
            properties = node.get("properties")
            if isinstance(properties, dict):
                for key, definition in properties.items():
                    walk(definition, f"{path}.{key}")
            if isinstance(node.get("items"), dict):
                walk(node["items"], f"{path}[]")
            for combiner in ("anyOf", "oneOf", "allOf"):
                for index, sub in enumerate(node.get(combiner, [])):
                    walk(sub, f"{path}.{combiner}[{index}]")
            if isinstance(node.get("additionalProperties"), dict):
                walk(node["additionalProperties"], f"{path}{{}}")

        walk({"properties": self._schema()}, self.schema_group)

        self.assertEqual([], suspect)

    def test_no_object_declares_the_same_key_twice(self):
        """A repeated key silently shadows the first one, defaults included."""
        _load_with_duplicates()


class WidgetSchemaCoverageTest(TypedDictCoverageMixin, unittest.TestCase):
    """Every widget the code reads has a schema object of its own."""

    schema_group = "widgets"
    typed_dicts = Widgets.__annotations__

    def setUp(self):
        self.widgets = _schema_widgets()

    def test_quick_settings_keeps_its_own_keys(self):
        """The regression: its properties were merged into ``network_usage``."""
        quick_settings = self.widgets["quick_settings"]["properties"]
        keys = ("hover_reveal", "toggles", "user", "controls", "media", "shortcuts")

        for key in keys:
            with self.subTest(key=key):
                self.assertIn(key, quick_settings)
                self.assertNotIn(key, self.widgets["network_usage"]["properties"])


class ModuleSchemaCoverageTest(TypedDictCoverageMixin, unittest.TestCase):
    """Same contract for the module sections."""

    schema_group = "modules"
    typed_dicts = Modules.__annotations__


def _schema_widgets() -> dict:
    return _load()["properties"]["widgets"]["properties"]


if __name__ == "__main__":
    unittest.main()

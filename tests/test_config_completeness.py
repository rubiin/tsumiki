"""The shipped config files must document every key the schema defines.

``config.toml`` and ``example/config.toml`` are the only places a user can read
what a key does, so a key that exists in ``tsumiki.schema.json`` but appears in
neither file is undocumented by default.
"""

import json
import os
import tomllib
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "tsumiki.schema.json")
CONFIG_FILES = ("config.toml", "example/config.toml")

# ``custom_widget`` is an array of entries, so its keys are checked per entry
# rather than per section.
ARRAY_KEYS = ("custom_widget",)


def load_schema() -> dict:
    with open(SCHEMA, encoding="utf-8") as handle:
        return json.load(handle)


def load_config(name: str) -> dict:
    with open(os.path.join(ROOT, name), "rb") as handle:
        return tomllib.load(handle)


def missing_keys(schema_props: dict, section: dict) -> set[str]:
    """Documentable schema keys under *schema_props* that *section* omits.

    A key with no ``default`` in the schema is skipped: there is no value to
    demonstrate, and inventing one changes behaviour (``custom_widget.signal``
    registers a real signal handler).
    """
    missing = set()
    for key, spec in schema_props.items():
        documentable = "default" in spec or spec.get("properties")
        if not documentable:
            continue
        if key not in section:
            missing.add(key)
            continue
        value = section[key]
        nested = spec.get("properties")
        if nested and isinstance(value, dict):
            missing |= {f"{key}.{sub}" for sub in missing_keys(nested, value)}
    return missing


class ConfigCompletenessTest(unittest.TestCase):
    """Every schema key appears in both shipped config files."""

    def setUp(self):
        self.schema = load_schema()["properties"]

    def _assert_complete(self, group: str) -> None:
        props = self.schema[group].get("properties", {})
        for name in CONFIG_FILES:
            section = load_config(name).get(group, {})
            with self.subTest(config=name, group=group):
                self.assertEqual(missing_keys(props, section), set())

    def test_general_keys_are_documented(self):
        self._assert_complete("general")

    def test_module_keys_are_documented(self):
        self._assert_complete("modules")

    def test_widget_keys_are_documented(self):
        self._assert_complete("widgets")

    def test_indexed_collection_items_are_documented(self):
        """A key inside a ``[[widgets.custom_widget]]`` entry counts too."""
        widgets = self.schema["widgets"]["properties"]
        for name in CONFIG_FILES:
            widgets_section = load_config(name).get("widgets", {})
            for array in ARRAY_KEYS:
                entries = widgets_section.get(array) or []
                item_props = widgets[array]["items"]["properties"]
                for index, entry in enumerate(entries):
                    with self.subTest(config=name, array=array, index=index):
                        self.assertEqual(missing_keys(item_props, entry), set())


class ConfigTypeTest(unittest.TestCase):
    """Values must match the schema's declared types and ranges."""

    def _type_matches(self, value, spec) -> bool:
        types = spec.get("type")
        if isinstance(types, list):
            return any(
                self._type_matches(value, {**spec, "type": one}) for one in types
            )
        return {
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "array": lambda v: isinstance(v, list),
            "object": lambda v: isinstance(v, dict),
        }.get(types, lambda _v: True)(value)

    def _walk(self, value, spec, path, errors) -> None:
        if not self._type_matches(value, spec):
            errors.append(
                f"{path}: expected {spec.get('type')}, got {type(value).__name__}"
            )
            return
        allowed = spec.get("enum")
        if allowed and isinstance(value, (str, int)) and value not in allowed:
            errors.append(f"{path}: {value!r} not in {allowed}")
        minimum = spec.get("minimum")
        if minimum is not None and isinstance(value, (int, float)) and value < minimum:
            errors.append(f"{path}: {value} < minimum {minimum}")
        if isinstance(value, dict):
            for key, child in spec.get("properties", {}).items():
                if key in value:
                    self._walk(value[key], child, f"{path}.{key}", errors)
        if isinstance(value, list) and isinstance(spec.get("items"), dict):
            for index, item in enumerate(value):
                self._walk(item, spec["items"], f"{path}[{index}]", errors)

    def test_values_match_the_schema(self):
        schema = load_schema()["properties"]
        for name in CONFIG_FILES:
            config = load_config(name)
            errors: list[str] = []
            for group in ("general", "modules", "widgets"):
                section = config.get(group, {})
                if not isinstance(section, dict):
                    continue
                for key, spec in schema[group].get("properties", {}).items():
                    if key in section:
                        self._walk(section[key], spec, f"{group}.{key}", errors)
            with self.subTest(config=name):
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

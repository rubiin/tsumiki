"""Config schema and widget validation utilities."""

import re
import string
from functools import lru_cache
from typing import Any

from fabric.utils import logger

from utils.colors import Colors
from utils.constants import GROUP_TYPES, SPECIAL_WIDGET_TYPES
from utils.functions import read_json_file


def _resolve_schema_ref(schema_node: Any, schema_root: dict) -> Any:
    """Resolve local JSON schema references."""

    while isinstance(schema_node, dict) and "$ref" in schema_node:
        ref = schema_node.get("$ref")
        if not isinstance(ref, str) or not ref.startswith("#/"):
            break

        resolved: Any = schema_root
        try:
            for part in ref[2:].split("/"):
                resolved = resolved[part]
        except (KeyError, TypeError):
            break

        schema_node = resolved

    return schema_node


def _schema_type_matches(value: Any, schema_type: Any) -> bool:
    """Return whether a value matches a JSON schema type declaration."""

    if schema_type is None:
        return True

    schema_types = {schema_type} if isinstance(schema_type, str) else set(schema_type)

    if value is None:
        return "null" in schema_types
    if isinstance(value, bool):
        return "boolean" in schema_types
    if isinstance(value, str):
        return "string" in schema_types
    if isinstance(value, dict):
        return "object" in schema_types
    if isinstance(value, list):
        return "array" in schema_types
    if isinstance(value, int):
        return "integer" in schema_types or "number" in schema_types
    if isinstance(value, float):
        return "number" in schema_types

    return False


def _format_config_value(value: Any) -> str:
    """Return a colored representation of a config value for error messages."""

    return f"{Colors.ERROR}{value!r}{Colors.RESET}"


def _format_allowed_values(values: list[Any]) -> str:
    """Return a colored, compact list of allowed config values."""

    return ", ".join(f"{Colors.OKGREEN}{item!r}{Colors.RESET}" for item in values)


def _validate_schema_enums(
    value: Any,
    schema_node: Any,
    schema_root: dict,
    path: str,
) -> None:
    """Validate enum and pattern constraints from a JSON schema node."""

    schema_node = _resolve_schema_ref(schema_node, schema_root)
    if not isinstance(schema_node, dict):
        return

    any_of = schema_node.get("anyOf")
    if isinstance(any_of, list):
        errors: list[str] = []
        for candidate in any_of:
            try:
                _validate_schema_enums(value, candidate, schema_root, path)
                break
            except ValueError as exc:
                errors.append(str(exc))
        else:
            raise ValueError(
                errors[0] if errors else f"{path}: invalid value {value!r}"
            )
        return

    one_of = schema_node.get("oneOf")
    if isinstance(one_of, list):
        matches = 0
        last_error = None
        for candidate in one_of:
            try:
                _validate_schema_enums(value, candidate, schema_root, path)
                matches += 1
            except ValueError as exc:
                last_error = str(exc)

        if matches != 1:
            raise ValueError(last_error or f"{path}: invalid value {value!r}")
        return

    schema_type = schema_node.get("type")
    if not _schema_type_matches(value, schema_type):
        return

    enum_values = schema_node.get("enum")
    if isinstance(enum_values, list) and value not in enum_values:
        raise ValueError(
            f"{path}: invalid enum value {_format_config_value(value)}; "
            f"allowed: {_format_allowed_values(enum_values)}"
        )

    pattern = schema_node.get("pattern")
    if (
        isinstance(pattern, str)
        and isinstance(value, str)
        and re.fullmatch(pattern, value) is None
    ):
        raise ValueError(f"{path}: invalid value {_format_config_value(value)}")

    if isinstance(value, (int, float)):
        minimum = schema_node.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            raise ValueError(
                f"{path}: {_format_config_value(value)} is below the minimum "
                f"of {minimum}"
            )
        maximum = schema_node.get("maximum")
        if isinstance(maximum, (int, float)) and value > maximum:
            raise ValueError(
                f"{path}: {_format_config_value(value)} is above the maximum "
                f"of {maximum}"
            )

    if isinstance(value, list):
        min_items = schema_node.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            raise ValueError(
                f"{path}: expected at least {min_items} item(s), got {len(value)}"
            )
        max_items = schema_node.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            raise ValueError(
                f"{path}: expected at most {max_items} item(s), got {len(value)}"
            )

    if isinstance(value, dict):
        properties = schema_node.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value:
                    child_path = f"{path}.{key}" if path else key
                    _validate_schema_enums(
                        value[key], child_schema, schema_root, child_path
                    )

        additional_properties = schema_node.get("additionalProperties")
        if isinstance(additional_properties, dict):
            for key, child_value in value.items():
                if key not in properties:
                    child_path = f"{path}.{key}" if path else key
                    _validate_schema_enums(
                        child_value, additional_properties, schema_root, child_path
                    )

    if isinstance(value, list):
        items = schema_node.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                item_path = f"{path}[{index}]" if path else f"[{index}]"
                _validate_schema_enums(item, items, schema_root, item_path)
        elif isinstance(items, list):
            for index, item_schema in enumerate(items):
                if index < len(value):
                    item_path = f"{path}[{index}]" if path else f"[{index}]"
                    _validate_schema_enums(
                        value[index], item_schema, schema_root, item_path
                    )


@lru_cache(maxsize=4)
def _load_schema(schema_file_path: str) -> dict:
    """Parse a JSON schema file, memoized per path.

    The schema is static for the process, so re-reading the ~122 KB file on
    every validation is pure waste.
    """
    schema = read_json_file(schema_file_path)
    if not isinstance(schema, dict):
        raise ValueError(f"Invalid JSON schema file: {schema_file_path}")
    return schema


def validate_config_enums(config_data: dict, schema_file_path: str) -> None:
    """Raise when a config value violates an enum or pattern constraint."""

    schema = _load_schema(schema_file_path)
    _validate_schema_enums(config_data, schema, schema, "config")


def _get_config_collection(parsed_data: dict, widget_type: str) -> list:
    """Return the collection for *widget_type* in *parsed_data*."""
    if widget_type == "group":
        return parsed_data.get("widget_groups", [])
    if widget_type == "collapsible":
        return parsed_data.get("collapsible_groups", [])
    if widget_type == "custom_widget":
        return parsed_data.get("widgets", {}).get("custom_widget", [])
    return []


def _validate_indexed_reference(
    identifier: str, collection: list, collection_name: str, section: str
) -> int:
    """Return the index *identifier* names in *collection*.

    String ``id`` matching is tried before the numeric reading, so an all-digit
    id like ``"2024"`` still resolves.
    """
    if not isinstance(collection, list):
        raise ValueError(f"{collection_name} must be an array")

    supports_id_lookup = collection_name in (
        "collapsible group",
        "custom widget",
        "widget group",
    )
    if supports_id_lookup:
        for idx, item in enumerate(collection):
            if isinstance(item, dict) and item.get("id") == identifier:
                return idx

    if identifier.isdigit():
        idx = int(identifier)

        if not (0 <= idx < len(collection)):
            raise ValueError(
                f"{collection_name.title()} index {idx} is out of range "
                f"in section {section}. "
                f"Available indices: 0-{len(collection) - 1}"
            )

        return idx

    if supports_id_lookup:
        raise ValueError(
            f"No {collection_name} with id '{identifier}' found in section {section}."
        )

    raise ValueError(
        f"Invalid {collection_name} reference '{identifier}' in section {section}. "
        "Must be a number."
    )


_COLLECTION_NAMES = {
    "group": "widget group",
    "collapsible": "collapsible group",
    "custom_widget": "custom widget",
}


def _validate_special_widget(
    widget_type: str, identifier: str, parsed_data: dict, section: str
) -> None:
    """Validate a ``@type:id`` reference in *section*."""
    collection = _get_config_collection(parsed_data, widget_type)
    collection_name = _COLLECTION_NAMES.get(widget_type, widget_type)
    _validate_indexed_reference(identifier, collection, collection_name, section)


def _validate_regular_widget(
    widget_spec: str,
    parsed_data: dict,
    default_config: dict,
    section: str,
) -> None:
    """Validate regular widget reference."""
    if _has_named_custom_widget(widget_spec, parsed_data):
        return

    widgets_list = default_config.get("widgets", {})
    if widget_spec not in widgets_list:
        raise ValueError(
            f"Invalid widget '{widget_spec}' in section {section}. "
            "Please check the widget name."
        )


def _has_named_custom_widget(widget_spec: str, parsed_data: dict) -> bool:
    """Check if widget spec points to a named custom widget."""
    if not widget_spec.startswith("custom/"):
        return False

    widgets_config = parsed_data.get("widgets", {})
    if not isinstance(widgets_config, dict):
        return False

    # Shape 1: widgets["custom/hello-world"]
    direct = widgets_config.get(widget_spec)
    if isinstance(direct, dict):
        return True

    custom_name = widget_spec.split("/", 1)[1] if "/" in widget_spec else widget_spec
    custom_widget = widgets_config.get("custom_widget", {})

    # Shape 2: widgets.custom_widget["hello-world"]
    if isinstance(custom_widget, dict):
        return isinstance(
            custom_widget.get(custom_name) or custom_widget.get(widget_spec),
            dict,
        )

    # Shape 3 (compat): [[widgets.custom_widget]] with optional `name`
    if isinstance(custom_widget, list):
        return any(
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and item.get("name") in (custom_name, widget_spec)
            for item in custom_widget
        )

    return False


def validate_widget_reference(
    widget_spec: str, parsed_data: dict, default_config: dict, section: str = "layout"
):
    """Validate any widget reference in *section*."""
    if widget_spec.startswith("@"):
        if ":" not in widget_spec:
            raise ValueError(
                f"Invalid reference format '{widget_spec}' in section {section}"
            )

        widget_type, identifier = widget_spec[1:].split(":", 1)

        if widget_type in SPECIAL_WIDGET_TYPES:
            _validate_special_widget(widget_type, identifier, parsed_data, section)
        else:
            raise ValueError(
                f"Unknown widget type '{widget_type}' in section {section}"
            )
    else:
        _validate_regular_widget(widget_spec, parsed_data, default_config, section)


def _get_named_format_keys(fmt: str) -> set[str]:
    """Return the set of named keys used in a Python format string."""
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(fmt)
        if field_name is not None and field_name != ""
    }


_VALID_LABEL_FORMATS = {
    "battery": {
        "label_format": set(
            ["percent", "time_remaining", "capacity", "temperature", "state"]
        ),
    },
    "network_usage": {
        "label_format": set(["download", "upload"]),
    },
    "weather": {
        "label_format": set(
            [
                "temperature",
                "condition",
                "location",
                "humidity",
                "wind_speed",
                "sunrise",
                "sunset",
            ]
        ),
    },
    "workspaces": {
        "label_format": set(["id"]),
    },
    "window_count": {
        "label_format": set(["count"]),
    },
    "mpris": {
        "label_format": set(["title", "artist", "album", "name"]),
    },
    # Widgets whose label also carries live state the widget feeds back in.
    "keyboard": {
        "label_format": set(["layout"]),
    },
    "language": {
        "label_format": set(["language"]),
    },
    "submap": {
        "label_format": set(["submap"]),
    },
    "updates": {
        "label_format": set(["total"]),
    },
    "hypridle": {
        "label_format": set(["state"]),
    },
    "hyprsunset": {
        "label_format": set(["state"]),
    },
    "bluetooth": {
        "label_format": set(["state"]),
    },
    "cloudflare_warp": {
        "label_format": set(["state"]),
    },
    "dns_switcher": {
        "label_format": set(["current_dns"]),
    },
    "microphone": {
        "label_format": set(["state"]),
    },
    "ocr": {
        "label_format": set(["lang"]),
    },
    "theme_switcher": {
        "label_format": set(["theme"]),
    },
    "usb_manager": {
        "label_format": set(["count"]),
    },
    "github_tray": {
        "label_format": set(["unread"]),
    },
    # These take no field at all: the config author writes the glyph straight
    # into ``label_format``, so anything in braces there is a typo.
    "breathe": {
        "label_format": set(),
    },
    "cheatsheet": {
        "label_format": set(),
    },
    "clipboard": {
        "label_format": set(),
    },
    "emoji_picker": {
        "label_format": set(),
    },
    "hyprpicker": {
        "label_format": set(),
    },
    "ip_monitor": {
        "label_format": set(),
    },
    "kanban": {
        "label_format": set(),
    },
    "launcher_button": {
        "label_format": set(),
    },
    "overview_button": {
        "label_format": set(),
    },
    "pomodoro": {
        "label_format": set(),
    },
    "power": {
        "label_format": set(),
    },
    "screenshot": {
        "label_format": set(),
    },
    "wallpaper": {
        "label_format": set(),
    },
    "world_clock": {
        "label_format": set(),
    },
}

# Indexed collections hold their config per entry rather than under ``widgets``,
# so an entry here labels its own toggle button, not a panel widget.
_VALID_COLLECTION_LABEL_FORMATS = {
    "collapsible_groups": {
        "label_format": set(),
    },
}

# A custom widget's formats only ever carry its command output.
_VALID_CUSTOM_WIDGET_FORMATS = {
    "label_format": {"value"},
    "tooltip_format": {"value"},
}


# Keys renamed after v4.8.3, mapped to what a config should use instead.
_RENAMED_WIDGET_KEYS = {
    "label": 'label_format (e.g. label_format = "\U000f0493")',
    "label_text": 'label_format (e.g. label_format = "\U000f0493")',
    "show_icon": 'label_format = "\U000f0493"',
}

# Top-level collections whose entries label a panel button, so they answer to the
# same renamed keys as ``widgets.<name>``.
_COLLECTIONS_WITH_RENAMED_KEYS = ("collapsible_groups",)

# ``widgets.cheatsheet`` kept only the panel button; the overlay's own settings
# moved to the module block. ``None`` marks a key dropped with no replacement.
_MOVED_CHEATSHEET_KEYS = {
    "title": "modules.cheatsheet.title",
    "columns": "modules.cheatsheet.columns",
    "groups_per_page": "modules.cheatsheet.groups_per_page",
    "max_entries_per_group": None,
}

_RENAMED_MODULE_KEYS = {
    ("osd", "duration"): "modules.osd.timeout",
    ("osd", "style"): (
        "nothing -- the OSD look now comes from orientation, anchor, "
        "transition_type and transition_duration"
    ),
}


def warn_deprecated_keys(parsed_data: dict) -> None:
    """Warn about keys renamed or removed after v4.8.3.

    Nothing rejects an undeclared key: ``validate_config_enums`` only walks the
    properties the schema does declare, so a stale key is dropped in silence.
    These warnings are the only signal a migrating user gets.
    """
    widgets = parsed_data.get("widgets", {})
    if isinstance(widgets, dict):
        for name, config in widgets.items():
            if isinstance(config, dict):
                _warn_renamed_widget_keys(f"widgets.{name}", config)
            elif isinstance(config, list):
                # custom_widget holds a list of entries.
                for index, entry in enumerate(config):
                    if isinstance(entry, dict):
                        _warn_renamed_widget_keys(f"widgets.{name}[{index}]", entry)

        _warn_moved_cheatsheet_keys(widgets.get("cheatsheet"))

    for collection_name in _COLLECTIONS_WITH_RENAMED_KEYS:
        entries = parsed_data.get(collection_name)
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if isinstance(entry, dict):
                _warn_renamed_widget_keys(f"{collection_name}[{index}]", entry)

    modules = parsed_data.get("modules", {})
    for (module, key), replacement in _RENAMED_MODULE_KEYS.items():
        config = modules.get(module) if isinstance(modules, dict) else None
        if isinstance(config, dict) and key in config:
            logger.warning(
                f"[Config] modules.{module}.{key} was renamed to {replacement}."
            )


def _warn_renamed_widget_keys(path: str, config: dict) -> None:
    for old_key, replacement in _RENAMED_WIDGET_KEYS.items():
        if old_key in config:
            logger.warning(
                f"[Config] {path}.{old_key} is no longer supported; use {replacement}."
            )


def _warn_moved_cheatsheet_keys(config) -> None:
    if not isinstance(config, dict):
        return

    for old_key, replacement in _MOVED_CHEATSHEET_KEYS.items():
        if old_key not in config:
            continue
        if replacement is None:
            logger.warning(
                f"[Config] widgets.cheatsheet.{old_key} was removed with no "
                "replacement."
            )
        else:
            logger.warning(
                f"[Config] widgets.cheatsheet.{old_key} moved to {replacement}; "
                "the key under widgets.cheatsheet is ignored."
            )


def _warn_unknown_format_keys(
    section: str, config: dict, formats: dict[str, set[str]]
) -> None:
    for config_key, valid_keys in formats.items():
        fmt = config.get(config_key)
        if not isinstance(fmt, str):
            continue
        try:
            used = _get_named_format_keys(fmt)
        except (ValueError, KeyError):
            logger.warning(f"[Config] {section}.{config_key}: invalid format")
            continue
        unknown = used - valid_keys
        if unknown:
            logger.warning(
                f"[Config] {section}.{config_key}: "
                f"unknown key(s) {sorted(unknown)!r}. "
                f"Valid keys: {sorted(valid_keys)!r}"
            )


def validate_format_strings(parsed_data: dict) -> None:
    """Warn when format strings in widget settings reference unknown keys."""
    widgets = parsed_data.get("widgets", {})
    for widget_name, formats in _VALID_LABEL_FORMATS.items():
        widget_cfg = widgets.get(widget_name, {})
        if not isinstance(widget_cfg, dict):
            continue
        _warn_unknown_format_keys(f"widgets.{widget_name}", widget_cfg, formats)

    for collection_name, formats in _VALID_COLLECTION_LABEL_FORMATS.items():
        for index, entry in enumerate(parsed_data.get(collection_name, []) or []):
            if isinstance(entry, dict):
                _warn_unknown_format_keys(f"{collection_name}[{index}]", entry, formats)

    _warn_custom_widget_format_keys(widgets.get("custom_widget"))


def _warn_custom_widget_format_keys(collection) -> None:
    """Custom widgets are keyed by index or by name, so both shapes are walked."""
    if isinstance(collection, list):
        entries = [
            (f"widgets.custom_widget[{index}]", entry)
            for index, entry in enumerate(collection)
        ]
    elif isinstance(collection, dict):
        entries = [
            (f"widgets.custom_widget.{name}", entry)
            for name, entry in collection.items()
        ]
    else:
        return

    for path, entry in entries:
        if isinstance(entry, dict):
            _warn_unknown_format_keys(path, entry, _VALID_CUSTOM_WIDGET_FORMATS)


def _validate_unique_ids(parsed_data: dict) -> None:
    """Warn when an indexed collection reuses an ``id``.

    Lookup resolves the first match, so a duplicate id leaves every later entry
    unreachable by name and addressable only by numeric index.
    """
    for widget_type in sorted(SPECIAL_WIDGET_TYPES):
        collection = _get_config_collection(parsed_data, widget_type)
        if not isinstance(collection, list):
            continue

        seen: dict[str, int] = {}
        for idx, item in enumerate(collection):
            identifier = item.get("id") if isinstance(item, dict) else None
            if not isinstance(identifier, str) or not identifier:
                continue
            if identifier in seen:
                logger.warning(
                    f"[Config] Duplicate {widget_type} id '{identifier}' at index "
                    f"{idx}; '{identifier}' resolves to index {seen[identifier]}. "
                    "Only the first entry is reachable by id."
                )
            else:
                seen[identifier] = idx


def validate_widgets(parsed_data, default_config):
    """Validates the widgets defined in the layout configuration."""
    _validate_unique_ids(parsed_data)

    layout = parsed_data.get("layout", {})

    for section_name, widgets in layout.items():
        if isinstance(widgets, list):
            for widget in widgets:
                validate_widget_reference(
                    widget, parsed_data, default_config, section_name
                )

    for group_type in GROUP_TYPES:
        groups = parsed_data.get(group_type, [])
        if isinstance(groups, list):
            for idx, group in enumerate(groups):
                if isinstance(group, dict) and "widgets" in group:
                    widgets = group["widgets"]
                    if not isinstance(widgets, (list, tuple)):
                        continue
                    for widget in widgets:
                        validate_widget_reference(
                            widget, parsed_data, default_config, f"{group_type}[{idx}]"
                        )

    warn_deprecated_keys(parsed_data)
    validate_format_strings(parsed_data)

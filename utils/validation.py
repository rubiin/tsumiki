"""Config schema and widget validation utilities."""

import json
import re
import string
from functools import lru_cache
from typing import Any

from fabric.utils import logger

from utils.colors import Colors
from utils.constants import GROUP_TYPES, SPECIAL_WIDGET_TYPES


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

    The schema is static for the life of the process, so re-reading and
    re-parsing the ~122 KB file on every validation (e.g. each
    ``reload_config``) is pure waste.
    """
    with open(schema_file_path, "r") as file:
        return json.load(file)


def validate_config_enums(config_data: dict, schema_file_path: str) -> None:
    """Raise when a config value violates an enum or pattern constraint."""

    schema = _load_schema(schema_file_path)
    _validate_schema_enums(config_data, schema, schema, "config")


def _get_config_collection(parsed_data: dict, widget_type: str) -> list:
    """Get collection for widget type - DRY principle."""
    if widget_type == "custom_button":
        return (
            parsed_data.get("widgets", {})
            .get("custom_button_group", {})
            .get("buttons", [])
        )
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
    """Helper function to validate indexed references (groups, buttons, etc.).

    Supports both numeric indices and string-based ``id`` lookup.  For
    supported collection types, string ``id`` matching takes priority over
    numeric index interpretation so that all-digit ids like ``"2024"``
    resolve correctly when a matching ``id`` field exists.
    """
    if not isinstance(collection, list):
        raise ValueError(f"{collection_name} must be an array")

    # For supported collection types, try string id lookup first. This takes
    # priority over numeric index interpretation so that all-digit ids
    # (e.g. id = "2024") work correctly.
    supports_id_lookup = collection_name in (
        "collapsible group",
        "custom widget",
        "custom button",
        "widget group",
    )
    if supports_id_lookup:
        for idx, item in enumerate(collection):
            if isinstance(item, dict) and item.get("id") == identifier:
                return idx

    # Fall back to numeric index lookup
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


# Pre-defined collection names mapping
_COLLECTION_NAMES = {
    "custom_button": "custom button",
    "group": "widget group",
    "collapsible": "collapsible group",
    "custom_widget": "custom widget",
}


def _validate_special_widget(
    widget_type: str, identifier: str, parsed_data: dict, section: str
) -> None:
    """Unified validation for special widget types - DRY principle."""
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
    """Unified validation for any widget reference using dispatcher pattern."""
    # Handle special references
    if widget_spec.startswith("@"):
        if ":" not in widget_spec:
            raise ValueError(
                f"Invalid reference format '{widget_spec}' in section {section}"
            )

        widget_type, identifier = widget_spec[1:].split(":", 1)

        # Unified validation for all special widget types
        if widget_type in SPECIAL_WIDGET_TYPES:
            _validate_special_widget(widget_type, identifier, parsed_data, section)
        else:
            raise ValueError(
                f"Unknown widget type '{widget_type}' in section {section}"
            )
    else:
        # Regular widget validation
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
        "label_format": set(["icon", "percent", "time_remaining"]),
    },
    "network_usage": {
        "label_format": set(["download", "upload"]),
    },
    "weather": {
        "label_format": set(["temperature", "condition"]),
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
}


# validate format strings in widget settings
def validate_format_strings(parsed_data: dict) -> None:
    """Warn when format strings in widget settings reference unknown keys."""
    widgets = parsed_data.get("widgets", {})
    for widget_name in _VALID_LABEL_FORMATS:
        widget_cfg = widgets.get(widget_name, {})
        if not isinstance(widget_cfg, dict):
            continue
        for config_key, valid_keys in _VALID_LABEL_FORMATS[widget_name].items():
            fmt = widget_cfg.get(config_key)
            if not isinstance(fmt, str):
                continue
            try:
                used = _get_named_format_keys(fmt)
            except (ValueError, KeyError):
                logger.warning(
                    f"[Config] widgets.{widget_name}.{config_key}: invalid format"
                )
                continue
            unknown = used - valid_keys
            if unknown:
                logger.warning(
                    f"[Config] widgets.{widget_name}.{config_key}: "
                    f"unknown key(s) {sorted(unknown)!r}. "
                    f"Valid keys: {sorted(valid_keys)!r}"
                )


def validate_widgets(parsed_data, default_config):
    """Validates the widgets defined in the layout configuration."""
    layout = parsed_data.get("layout", {})

    # Validate widgets in all sections
    for section_name, widgets in layout.items():
        if isinstance(widgets, list):
            for widget in widgets:
                validate_widget_reference(
                    widget, parsed_data, default_config, section_name
                )

    # Validate widgets inside groups
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

    validate_format_strings(parsed_data)

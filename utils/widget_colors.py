"""Helpers for per-widget color config merge, validation, and resolution.

Invalid or malformed values are ignored for the affected field (never raise)
and, when context is available, logged with a warning.
"""

from __future__ import annotations

import contextlib
import re
from typing import Any, Mapping

from loguru import logger

_HEX_RE = re.compile(
    r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"
)
_ALPHA_RE = r"(?:0|1|0?\.\d+|\d+(?:\.\d+)?)"
_RGB_RE = re.compile(r"^rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)$")
_RGBA_RE = re.compile(
    rf"^rgba\(\s*\d{{1,3}}\s*,\s*\d{{1,3}}\s*,\s*\d{{1,3}}\s*,\s*{_ALPHA_RE}\s*\)$"
)
_HSL_RE = re.compile(r"^hsl\(\s*\d{1,3}\s*,\s*\d{1,3}%\s*,\s*\d{1,3}%\s*\)$")
_HSLA_RE = re.compile(
    rf"^hsla\(\s*\d{{1,3}}\s*,\s*\d{{1,3}}%\s*,\s*\d{{1,3}}%\s*,\s*{_ALPHA_RE}\s*\)$"
)
_TOKEN_RE = re.compile(r"^[a-z0-9_-]+$")
_SCSS_VAR_RE = re.compile(r"^\s*\$([a-zA-Z0-9_-]+)\s*:\s*([^;]+);\s*$")

_COLOR_FIELDS = ("background", "foreground")
_COLOR_STATES = ("hover", "active")


def is_color_literal(value: Any) -> bool:
    """Return True if value is a supported literal color string."""
    if not isinstance(value, str):
        return False
    return bool(
        _HEX_RE.match(value)
        or _RGB_RE.match(value)
        or _RGBA_RE.match(value)
        or _HSL_RE.match(value)
        or _HSLA_RE.match(value)
    )


def is_theme_token(value: Any, theme_tokens: set[str] | None = None) -> bool:
    """Return True if value is a valid theme token name."""
    if not isinstance(value, str) or not value:
        return False
    if not _TOKEN_RE.match(value):
        return False
    if theme_tokens is not None:
        return value in theme_tokens
    return True


def _format_color_context(context: Mapping[str, Any] | None) -> str:
    if not context:
        return ""
    parts = []
    for key in ("widget_type", "instance_id", "state", "field"):
        value = context.get(key)
        if value is not None and value != "":
            parts.append(f"{key}={value}")
    return f" ({', '.join(parts)})" if parts else ""


def _is_unset_color_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _log_invalid_color(value: Any, context: Mapping[str, Any] | None) -> None:
    if _is_unset_color_value(value):
        return
    with contextlib.suppress(Exception):
        logger.warning(
            "[WidgetColors] Ignoring invalid color value "
            f"{value!r}{_format_color_context(context)}"
        )


def normalize_color_value(
    value: Any,
    theme_tokens: set[str] | None = None,
    *,
    warn_context: Mapping[str, Any] | None = None,
) -> str | None:
    """Return a valid literal or token name, else None. Never raises."""
    try:
        if _is_unset_color_value(value):
            return None
        if not isinstance(value, str):
            _log_invalid_color(value, warn_context)
            return None
        if is_color_literal(value):
            return value
        if is_theme_token(value, theme_tokens):
            return value
        _log_invalid_color(value, warn_context)
        return None
    except Exception:
        _log_invalid_color(value, warn_context)
        return None


def resolve_color_value(
    value: Any,
    theme_map: dict[str, str],
    *,
    warn_context: Mapping[str, Any] | None = None,
) -> str | None:
    """Resolve a token via theme_map or passthrough a literal. Invalid -> None."""
    normalized = normalize_color_value(value, warn_context=warn_context)
    if normalized is None:
        return None
    if is_color_literal(normalized):
        return normalized
    resolved = theme_map.get(normalized)
    if resolved is None:
        _log_invalid_color(normalized, warn_context)
    return resolved


def parse_scss_theme_variables(text: str) -> dict[str, str]:
    """Parse `$name: value;` assignments from SCSS theme content."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = _SCSS_VAR_RE.match(line)
        if match:
            result[match.group(1)] = match.group(2).strip()
    return result


def format_settings_color_value(
    value: Any,
    theme_tokens: set[str] | None = None,
    *,
    warn_context: Mapping[str, Any] | None = None,
) -> str | None:
    """Format a color token as `theme.$token` or return literal as-is."""
    normalized = normalize_color_value(
        value, theme_tokens=theme_tokens, warn_context=warn_context
    )
    if normalized is None:
        return None
    if is_color_literal(normalized):
        return normalized
    return f"theme.${normalized}"


def _clean_field(
    value: Any,
    theme_tokens: set[str] | None = None,
    warn_context: Mapping[str, Any] | None = None,
) -> str | None:
    """Return value if it is a valid color literal/token, else None.

    Invalid/malformed values are treated as unset so type/defaults can apply.
    """
    return normalize_color_value(
        value, theme_tokens=theme_tokens, warn_context=warn_context
    )


def _merge_state(
    type_state: Any,
    instance_state: Any,
    theme_tokens: set[str] | None = None,
    warn_context: Mapping[str, Any] | None = None,
) -> dict:
    merged: dict[str, str] = {}
    type_state = type_state if isinstance(type_state, dict) else {}
    instance_state = instance_state if isinstance(instance_state, dict) else {}
    for field in _COLOR_FIELDS:
        value = None
        if field in instance_state:
            value = _clean_field(
                instance_state.get(field),
                theme_tokens=theme_tokens,
                warn_context=(
                    {**(warn_context or {}), "field": field} if warn_context else None
                ),
            )
        if value is None:
            value = _clean_field(
                type_state.get(field),
                theme_tokens=theme_tokens,
                warn_context=(
                    {**(warn_context or {}), "field": field} if warn_context else None
                ),
            )
        if value is not None:
            merged[field] = value
    return merged


def merge_widget_colors(
    type_colors: dict | None,
    instance_colors: dict | None,
    theme_tokens: set[str] | None = None,
    *,
    warn_context: Mapping[str, Any] | None = None,
) -> dict:
    """Per-field merge for background/foreground and hover/active substates."""
    type_colors = type_colors if isinstance(type_colors, dict) else {}
    instance_colors = instance_colors if isinstance(instance_colors, dict) else {}
    merged: dict[str, Any] = {}

    for field in _COLOR_FIELDS:
        value = None
        if field in instance_colors:
            value = _clean_field(
                instance_colors.get(field),
                theme_tokens=theme_tokens,
                warn_context=(
                    {**(warn_context or {}), "field": field} if warn_context else None
                ),
            )
        if value is None:
            value = _clean_field(
                type_colors.get(field),
                theme_tokens=theme_tokens,
                warn_context=(
                    {**(warn_context or {}), "field": field} if warn_context else None
                ),
            )
        if value is not None:
            merged[field] = value

    for state in _COLOR_STATES:
        state_ctx = {**(warn_context or {}), "state": state} if warn_context else None
        state_merged = _merge_state(
            type_colors.get(state),
            instance_colors.get(state),
            theme_tokens=theme_tokens,
            warn_context=state_ctx,
        )
        if state_merged:
            merged[state] = state_merged

    return merged


def _emit_value(
    value: Any,
    theme_map: dict[str, str] | None,
    as_theme_refs: bool,
    warn_context: Mapping[str, Any] | None = None,
) -> str | None:
    normalized = normalize_color_value(value, warn_context=warn_context)
    if normalized is None:
        return None
    if is_color_literal(normalized):
        return normalized
    # token
    if as_theme_refs:
        return f"theme.${normalized}"
    resolved = (theme_map or {}).get(normalized)
    if resolved is None:
        _log_invalid_color(normalized, warn_context)
    return resolved


def _build_rule(selector: str, bg: str | None, fg: str | None) -> str:
    if bg is None and fg is None:
        return ""
    decls = []
    if bg is not None:
        decls.append(f"background-color: {bg};")
    if fg is not None:
        decls.append(f"color: {fg};")
    rules = [f"{selector} {{ {' '.join(decls)} }}"]
    if fg is not None:
        inner = (
            f"{selector} .panel-text, {selector} .panel-font-icon, "
            f"{selector} image, {selector} label"
        )
        rules.append(f"{inner} {{ color: {fg}; }}")
    return "\n".join(rules)


def build_widget_colors_css(
    selector: str,
    colors: dict,
    theme_map: dict[str, str] | None = None,
    as_theme_refs: bool = False,
    *,
    warn_context: Mapping[str, Any] | None = None,
) -> str:
    """Emit scoped CSS for normal/hover/active color overrides."""
    if not isinstance(colors, dict):
        return ""

    blocks: list[str] = []

    base_bg = _emit_value(
        colors.get("background"),
        theme_map,
        as_theme_refs,
        {**(warn_context or {}), "field": "background"} if warn_context else None,
    )
    base_fg = _emit_value(
        colors.get("foreground"),
        theme_map,
        as_theme_refs,
        {**(warn_context or {}), "field": "foreground"} if warn_context else None,
    )
    base_rule = _build_rule(selector, base_bg, base_fg)
    if base_rule:
        blocks.append(base_rule)

    hover = colors.get("hover") if isinstance(colors.get("hover"), dict) else {}
    hover_ctx = {**(warn_context or {}), "state": "hover"} if warn_context else None
    hover_bg = _emit_value(
        hover.get("background"),
        theme_map,
        as_theme_refs,
        {**hover_ctx, "field": "background"} if hover_ctx else None,
    )
    hover_fg = _emit_value(
        hover.get("foreground"),
        theme_map,
        as_theme_refs,
        {**hover_ctx, "field": "foreground"} if hover_ctx else None,
    )
    hover_rule = _build_rule(f"{selector}:hover", hover_bg, hover_fg)
    if hover_rule:
        blocks.append(hover_rule)

    active = colors.get("active") if isinstance(colors.get("active"), dict) else {}
    active_ctx = {**(warn_context or {}), "state": "active"} if warn_context else None
    active_bg = _emit_value(
        active.get("background"),
        theme_map,
        as_theme_refs,
        {**active_ctx, "field": "background"} if active_ctx else None,
    )
    active_fg = _emit_value(
        active.get("foreground"),
        theme_map,
        as_theme_refs,
        {**active_ctx, "field": "foreground"} if active_ctx else None,
    )
    active_rule = _build_rule(f"{selector}.active", active_bg, active_fg)
    if active_rule:
        blocks.append(active_rule)

    return "\n".join(blocks)


def _sanitize_instance_id(instance_id: Any) -> str | None:
    """Return a safe CSS token for instance targeting, or None."""
    if not isinstance(instance_id, str):
        return None
    instance_id = instance_id.strip()
    if not instance_id:
        return None
    safe = re.sub(r"[^a-zA-Z0-9_-]", "-", instance_id)
    return safe or None


def get_widget_instance_selector(
    widget_type: str, instance_id: str | None, widget_name: str | None = None
) -> str | None:
    """Return a stable selector for a specific widget instance.

    If *widget_name* is provided it is used as the base GTK id selector so the
    caller can control targeting; otherwise targets ``#<widget_type>`` with an
    instance class when an instance id is available.
    """
    base = widget_name or widget_type
    if not base:
        return None
    safe_id = _sanitize_instance_id(instance_id)
    if safe_id is None:
        return f"#{base}"
    # Prefer provided unique widget name as direct id selector.
    if widget_name and widget_name != widget_type:
        return f"#{widget_name}"
    return f"#{base}.instance-{safe_id}"


def _clean_colors_only(
    colors: Any,
    theme_tokens: set[str] | None = None,
    warn_context: Mapping[str, Any] | None = None,
) -> dict:
    """Return only valid color fields/states from *colors* (no merging)."""
    if not isinstance(colors, dict):
        return {}
    cleaned: dict[str, Any] = {}

    for field in _COLOR_FIELDS:
        value = _clean_field(
            colors.get(field),
            theme_tokens=theme_tokens,
            warn_context=(
                {**(warn_context or {}), "field": field} if warn_context else None
            ),
        )
        if value is not None:
            cleaned[field] = value

    for state in _COLOR_STATES:
        state_val = colors.get(state)
        if not isinstance(state_val, dict):
            if state in colors and not _is_unset_color_value(state_val):
                _log_invalid_color(
                    state_val,
                    {**(warn_context or {}), "state": state} if warn_context else None,
                )
            continue
        state_ctx = {**(warn_context or {}), "state": state} if warn_context else None
        state_cleaned: dict[str, str] = {}
        for field in _COLOR_FIELDS:
            value = _clean_field(
                state_val.get(field),
                theme_tokens=theme_tokens,
                warn_context=(
                    {**state_ctx, "field": field} if state_ctx else None
                ),
            )
            if value is not None:
                state_cleaned[field] = value
        if state_cleaned:
            cleaned[state] = state_cleaned

    return cleaned


def resolve_widget_instance_colors(
    widget_type: str,
    instance_id: str | None,
    styling_config: dict | None,
    theme_tokens: set[str] | None = None,
    *,
    warn: bool = False,
) -> dict:
    """Return effective per-instance runtime color overrides.

    Returns only the valid fields defined in the instance's override block (not
    merged with type-level colors) so type-level SCSS remains the source for
    inherited fields. Returns an empty dict when no instance-specific override
    exists or when no valid override fields remain, so callers can skip creating
    a runtime provider. Token values are preserved for later theme re-resolution.
    """
    if not widget_type or not isinstance(styling_config, dict):
        return {}
    bar = styling_config.get("bar", {})
    if not isinstance(bar, dict):
        return {}
    widgets = bar.get("widgets", {})
    if not isinstance(widgets, dict):
        return {}
    type_cfg = widgets.get(widget_type, {})
    if not isinstance(type_cfg, dict):
        return {}

    overrides = type_cfg.get("overrides", {})
    if (
        not instance_id
        or not isinstance(overrides, dict)
        or instance_id not in overrides
    ):
        return {}

    override_entry = overrides.get(instance_id)
    instance_colors = (
        override_entry.get("colors") if isinstance(override_entry, dict) else None
    )
    warn_context = (
        {"widget_type": widget_type, "instance_id": instance_id} if warn else None
    )
    # Runtime provider should only emit instance-defined overrides; type-level
    # fields stay in SCSS to avoid pinning/diverging semantics.
    return _clean_colors_only(
        instance_colors if isinstance(instance_colors, dict) else {},
        theme_tokens=theme_tokens,
        warn_context=warn_context,
    )

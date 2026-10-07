from fabric.hyprland.widgets import HyprlandActiveWindow
from fabric.utils import FormattedString, logger, re, truncate

from shared.widget_container import BaseWidget
from utils.constants import WINDOW_TITLE_MAP

# Pre-compile WINDOW_TITLE_MAP at module load, capped to bound custom patterns.
_COMPILED_PATTERNS: dict[str, re.Pattern | None] = {}
_MAX_COMPILED_PATTERNS = 50


class WindowTitleWidget(HyprlandActiveWindow, BaseWidget):
    """a widget that displays the title of the active window."""

    def __init__(self, **kwargs):
        # Read config first: the parent's initial window sync formats its label
        # through ``_get_title``, which needs the widget config already in place.
        self._init_widget_settings("window_title")
        super().__init__(
            name="window_title",
            style_classes="panel-button",
            formatter=FormattedString(
                "{ get_title(win_title, win_class) }",
                get_title=self._get_title,
            ),
            **kwargs,
        )
        self._connect_hover_reveal()
        self.connect("state-flags-changed", self._sync_hover_cursor)

        self.connect("notify::label", lambda *_: self._sync_occupancy())
        self._sync_occupancy()

    def _sync_occupancy(self) -> None:
        """Collapse the button while the active workspace holds no window.

        An empty label still carries the ``.panel-button`` padding and
        background, so a workspace with nothing focused left a blank pill on
        the bar.
        """
        self.set_visible(bool(self.get_label()))

    def _set_tooltip(self, text: str | None) -> None:
        """Write or clear the tooltip so it never outlives its window.

        ``set_tooltip_if_enabled`` skips the write when tooltips are switched
        off, which is right for setting text but would leave a stale title in
        place once the workspace runs out of windows.
        """
        if text is None:
            self.set_tooltip_text(None)
        else:
            self.set_tooltip_if_enabled(text, default=True)

    def _get_title(self, win_title: str, win_class: str):
        # Fabric reports "unknown" when j/activewindow has no class key.
        if not win_class or win_class == "unknown":
            self._set_tooltip(None)
            return ""

        mappings_enabled = self.config.get("mappings", True)
        trunc = self.config.get("truncation", True)
        trunc_size = self.config.get("truncation_size", 50)

        if not mappings_enabled:
            self._set_tooltip(win_title)
            return truncate(win_title, trunc_size) if trunc else win_title

        custom_map = self.config.get("title_map", [])
        icon_enabled = self.config.get("icon", True)

        self._set_tooltip(win_title)

        win_title = truncate(win_title, trunc_size) if trunc else win_title
        merged_titles = WINDOW_TITLE_MAP + (
            custom_map if isinstance(custom_map, list) else []
        )

        win_class_lower = win_class.lower()
        for pattern, icon, name in merged_titles:
            compiled = self._get_compiled_pattern(pattern)
            if compiled is None:
                logger.warning(f"[window_title] Invalid regex '{pattern}'")
                continue
            if compiled.search(win_class_lower):
                return f"{icon} {name}" if icon_enabled else name

        fallback = (
            win_class_lower
            if self.config.get("fallback", "class") == "class"
            else win_title.lower()
        )
        fallback = truncate(fallback, trunc_size) if trunc else fallback
        # A configured glyph may be empty, which drops it without a second key.
        fallback_icon = self.config.get("fallback_icon", "\U000f08c6")
        return f"{fallback_icon} {fallback}" if fallback_icon else fallback

    def _get_compiled_pattern(self, pattern: str) -> re.Pattern | None:
        """Get or compile a regex pattern, caching the result."""
        if pattern not in _COMPILED_PATTERNS:
            if len(_COMPILED_PATTERNS) >= _MAX_COMPILED_PATTERNS:
                _COMPILED_PATTERNS.clear()
            try:
                _COMPILED_PATTERNS[pattern] = re.compile(pattern)
            except re.error:
                _COMPILED_PATTERNS[pattern] = None
        return _COMPILED_PATTERNS[pattern]

from fabric.hyprland.widgets import HyprlandActiveWindow
from fabric.utils import FormattedString, logger, re, truncate

from shared.widget_container import ButtonWidget
from utils.constants import WINDOW_TITLE_MAP

# Pre-compile WINDOW_TITLE_MAP at module load, capped to bound custom patterns.
_COMPILED_PATTERNS: dict[str, re.Pattern | None] = {}
_MAX_COMPILED_PATTERNS = 50


class WindowTitleWidget(ButtonWidget):
    """a widget that displays the title of the active window."""

    def __init__(self, **kwargs):
        super().__init__(name="window_title", **kwargs)

        active_window = HyprlandActiveWindow

        # Create an ActiveWindow widget to track the active window
        self.active_window = active_window(
            name="window",
            formatter=FormattedString(
                "{ get_title(win_title, win_class) }",
                get_title=self._get_title,
            ),
        )

        # Add the ActiveWindow widget as a child
        self.container_box.children = self.active_window

    def _get_title(self, win_title: str, win_class: str):
        # Fabric reports "unknown" when j/activewindow has no class key.
        if not win_class or win_class == "unknown":
            return ""

        mappings_enabled = self.config.get("mappings", True)
        trunc = self.config.get("truncation", True)
        trunc_size = self.config.get("truncation_size", 50)

        if not mappings_enabled:
            return truncate(win_title, trunc_size) if trunc else win_title

        custom_map = self.config.get("title_map", [])
        icon_enabled = self.config.get("icon", True)

        if self.config.get("tooltip", True) and self.tooltips_enabled:
            self.set_tooltip_text(win_title)

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
        return f"󰣆 {fallback}"

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

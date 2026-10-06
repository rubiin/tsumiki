"""Reusable mixins for reducing code duplication across widgets."""

from collections import deque
from typing import Callable

from fabric.widgets.label import Label

from utils.widget_utils import create_progress, get_bar_graph, nerd_font_icon


class PopoverMixin:
    """Mixin for lazy popover initialization."""

    _popup = None
    _popover_content_factory: Callable | None = None

    def setup_popover(
        self,
        content_factory: Callable,
        connect_clicked: bool = True,
        on_close_callback: Callable | None = None,
    ) -> None:
        """Register the popover content factory; the popover is built on first use."""
        self._popover_content_factory = content_factory
        self._popover_on_close = on_close_callback

        if connect_clicked:
            self.connect("clicked", self.show_popover)

    def show_popover(self, *_) -> None:
        """Show the popover, creating it lazily on first use."""
        if self._popup is None and self._popover_content_factory is not None:
            from .popover import Popover

            # Children reference self._popup, so it must exist before they build.
            self._popup = Popover(point_to=self)
            self._popup.set_content(self._popover_content_factory())

            if self._popover_on_close:
                self._popup.connect("popover-closed", self._popover_on_close)
            else:
                self._popup.connect(
                    "popover-closed", lambda *_: self.remove_style_class("active")
                )

        if self._popup:
            self._popup.open()
            self.add_style_class("active")

    def hide_popover(self) -> None:
        """Hide the popover if it exists."""
        if self._popup:
            self._popup.hide()
            self.remove_style_class("active")

    def toggle_popover(self) -> None:
        """Toggle popover visibility."""
        if self._popup and self._popup.get_visible():
            self.hide_popover()
        else:
            self.show_popover()

    @property
    def popup(self):
        """Property for backward compatibility with existing code."""
        return self._popup

    @popup.setter
    def popup(self, value):
        """Setter for backward compatibility."""
        self._popup = value


class StatDisplayMixin:
    """Mixin for stat widgets sharing the label/graph/progress display modes."""

    # DO NOT USE SLOTS HERE

    _stat_icon: str = "󰕸"
    _stat_name: str = "stat"

    _VALID_STAT_MODES = ("label", "graph", "progress")

    def _normalize_stat_mode(self, mode: str) -> str:
        """Map aliases and invalid values to a supported mode."""
        normalized = str(mode).strip().lower()
        if normalized == "circular":
            normalized = "progress"

        if normalized not in self._VALID_STAT_MODES:
            return "label"

        return normalized

    def _get_cycle_modes(self) -> list[str]:
        """Resolve the mode cycle order from config."""
        raw_modes = self.config.get("cycle_modes", self._VALID_STAT_MODES)
        if not isinstance(raw_modes, (list, tuple)):
            raw_modes = self._VALID_STAT_MODES

        modes = []
        for mode in raw_modes:
            normalized = self._normalize_stat_mode(mode)
            if normalized not in modes:
                modes.append(normalized)

        return modes or ["label"]

    def _render_current_mode(self) -> None:
        """Rebuild children for the currently selected display mode."""
        if self.current_mode == "graph":
            self._setup_graph_mode(self._stat_container)
        elif self.current_mode == "progress":
            self._setup_progress_mode(self._stat_container)
        else:
            self._setup_label_mode(self._stat_container)

    def setup_stat_display(self, container) -> None:
        """Setup the display mode (graph, progress, or label) based on config."""
        self._stat_container = container
        self._last_stat_value = 0.0
        self._last_stat_label = "0%"

        self._cycle_modes = self._get_cycle_modes()
        self.current_mode = self._normalize_stat_mode(self.config.get("mode", "label"))

        if self.current_mode not in self._cycle_modes:
            self._cycle_modes.insert(0, self.current_mode)

        self._render_current_mode()

        if self.config.get("cycle_mode_on_click", True):
            self.connect("clicked", self.cycle_stat_mode)

    def cycle_stat_mode(self, *_) -> None:
        """Cycle to the next display mode and refresh current value."""
        if len(self._cycle_modes) <= 1:
            return

        current_index = self._cycle_modes.index(self.current_mode)
        self.current_mode = self._cycle_modes[
            (current_index + 1) % len(self._cycle_modes)
        ]

        self._render_current_mode()
        self.update_stat_display(self._last_stat_value, self._last_stat_label)

    def _setup_graph_mode(self, container) -> None:
        """Setup graph display mode with bar characters."""
        self._graph_maxlen = self.config.get("graph_length", 4)
        self.graph_values = deque(maxlen=self._graph_maxlen)

        self.level_label = Label(
            label="0%",
            style_classes=[
                "panel-text",
                "stat-graph",
            ],
            style=f"min-width: {self._graph_maxlen * 10}px;",
        )
        container.children = self.level_label

    def _setup_progress_mode(self, container) -> None:
        """Setup circular progress bar display mode."""
        self.icon = self._build_stat_icon()

        self.progress_bar = create_progress(name="stat-circle", child=self.icon)

        container.children = self.progress_bar

    def _setup_label_mode(self, container) -> None:
        """Setup text label display mode with icon."""
        self.icon = self._build_stat_icon()

        self.level_label = Label(
            label="0%",
            style_classes="panel-text",
        )
        container.children = ((self.icon,) if self.icon else ()) + (self.level_label,)

    def _build_stat_icon(self):
        """The stat glyph from ``label_format``, or *None* when it is empty.

        These widgets have no other format field, so the string is the glyph.
        """
        glyph = self.config.get("label_format", self._stat_icon)
        if not isinstance(glyph, str) or not glyph.strip():
            return None

        return nerd_font_icon(
            icon=glyph,
            props={"style_classes": ["panel-font-icon"]},
        )

    def update_stat_display(self, value: float, label_text: str) -> None:
        """Update the stat display based on current mode.

        *value* is 0-100 for percentage; *label_text* shows in label mode.
        """
        self._last_stat_value = value
        self._last_stat_label = label_text

        if self.current_mode == "graph":
            self.graph_values.append(get_bar_graph(value))
            self.level_label.set_label("".join(self.graph_values))
        elif self.current_mode == "progress":
            normalized_value = value / 100
            self.progress_bar.set_value(normalized_value)
            self.progress_bar.animate_value(normalized_value)
        else:
            self.level_label.set_label(label_text)

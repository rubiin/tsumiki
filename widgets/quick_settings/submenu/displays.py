from collections.abc import Callable
from time import monotonic

from fabric.utils import GLib, Gtk, logger
from fabric.widgets.box import Box
from fabric.widgets.label import Label

from shared.buttons import QSChevronButton, ScanButton
from shared.list import ListBox, SubmenuRowMixin, add_list_row
from shared.submenu import QuickSubMenu, scrolled_list_content
from utils.functions import safe_disconnect
from utils.hyprland import hyprland_service
from utils.i18n import _
from utils.icons import get_text_icon
from utils.widget_utils import nerd_font_icon

_MONITOR_ICON = get_text_icon("ui.monitor", "󰍹")
_FOCUSED_ICON = get_text_icon("ui.tick", "")

_FADE_FRAME_MS = 16
_FADE_MS = 150


def monitor_summary(monitor: dict) -> str:
    """Format resolution, refresh rate and scale for a ``j/monitors`` entry."""
    width = monitor.get("width", 0)
    height = monitor.get("height", 0)
    refresh = round(float(monitor.get("refreshRate", 0) or 0))
    scale = float(monitor.get("scale", 1) or 1)

    summary = f"{width}x{height} @ {refresh} Hz"
    if scale != 1:
        summary += f" · {scale:g}x"
    return summary


class DisplayItem(Gtk.ListBoxRow, SubmenuRowMixin):
    """One monitor row; activating it moves focus to that output."""

    def __init__(
        self,
        monitor: dict,
        on_selected: Callable[["DisplayItem"], None],
        **kwargs,
    ):
        self.monitor_name = str(monitor.get("name", ""))
        self._on_selected = on_selected

        self._focus_icon = nerd_font_icon(
            icon=_FOCUSED_ICON,
            props={"style_classes": ["panel-font-icon"]},
        )
        self._focus_icon.set_visible(False)
        self._focus_icon_shown = False

        self._content_box = Box(
            orientation="h",
            spacing=10,
            children=[
                nerd_font_icon(
                    icon=_MONITOR_ICON,
                    props={"style_classes": ["panel-font-icon"]},
                ),
                Box(
                    orientation="v",
                    spacing=2,
                    h_expand=True,
                    children=[
                        Label(
                            label=self.monitor_name,
                            style_classes="submenu-item-label",
                            h_align="start",
                            ellipsization="end",
                        ),
                        Label(
                            label=monitor_summary(monitor),
                            style_classes="panel-text",
                            h_align="start",
                            ellipsization="end",
                        ),
                    ],
                ),
                self._focus_icon,
            ],
        )

        super().__init__(visible=True, **kwargs)
        self.set_name("display-item")
        self.setup_submenu_row(self._content_box, "display-item")
        self.set_active(bool(monitor.get("focused", False)))

    def select(self):
        self._on_selected(self)

    def set_active(self, active: bool):
        self._set_focus_icon(active)
        self.set_row_active(active)

    def _set_focus_icon(self, visible: bool):
        if visible == self._focus_icon_shown:
            return
        self._focus_icon_shown = visible
        if not visible:
            self._focus_icon.set_visible(False)
            return

        self._focus_icon.set_opacity(0.0)
        self._focus_icon.set_visible(True)
        started = monotonic()

        def step() -> bool:
            progress = min(1.0, (monotonic() - started) * 1000 / _FADE_MS)
            self._focus_icon.set_opacity(progress)
            return progress < 1.0

        GLib.timeout_add(_FADE_FRAME_MS, step)


class DisplaysSubMenu(QuickSubMenu):
    """A submenu listing connected outputs, with click-to-focus."""

    def __init__(self, **kwargs):
        self.scan_button = ScanButton()
        self.scan_button.connect("clicked", lambda *_: self.refresh())

        self.monitor_list = ListBox(
            name="display-list",
            visible=True,
            selection_mode="none",
        )

        super().__init__(
            title=_("widget.quick_settings.displays.title"),
            title_icon=_MONITOR_ICON,
            scan_button=self.scan_button,
            child=scrolled_list_content(self.monitor_list, min_height=120),
            **kwargs,
        )

        self._items: list[DisplayItem] = []
        self._loading = False
        self._handler_ids: list[int] = []

        self.monitor_list.connect("row-activated", self._on_row_activated)

        for event, callback in (
            ("event::focusedmonv2", self._on_focus_changed),
            ("event::monitoraddedv2", self._on_monitor_added),
            ("event::monitorremoved", self._on_monitor_removed),
        ):
            self._handler_ids.append(hyprland_service.connect(event, callback))

        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, *_):
        if self._handler_ids:
            for handler_id in self._handler_ids:
                safe_disconnect(hyprland_service, handler_id)
            self._handler_ids = []

    def prepare_content(self):
        """Fetch outputs before expanding so the list has its real height."""
        self.refresh()

    def refresh(self):
        """Re-query the outputs; a request already in flight wins."""
        if self._loading:
            return
        self._loading = True
        self.scan_button.play_animation()
        hyprland_service.get_monitors_async(self._on_monitors)

    def _on_monitors(self, monitors):
        self._loading = False
        if monitors is None:
            logger.warning("[Displays] Failed to fetch monitors")
            return

        self._items = [
            DisplayItem(monitor=monitor, on_selected=self._on_item_selected)
            for monitor in monitors
            if not monitor.get("disabled", False)
        ]
        self.monitor_list.remove_all()
        if not self._items:
            row = Gtk.ListBoxRow(visible=True)
            row.add(
                Label(
                    label=_("widget.quick_settings.displays.none"),
                    style_classes="panel-text",
                    h_align="start",
                )
            )
            add_list_row(self.monitor_list, row)
            return

        for item in self._items:
            add_list_row(self.monitor_list, item)

    def _on_row_activated(self, _listbox: ListBox, row: Gtk.ListBoxRow):
        if isinstance(row, DisplayItem):
            row.select()

    def _on_item_selected(self, item: DisplayItem):
        for other in self._items:
            other.set_active(other is item)
        hyprland_service.focus_monitor(item.monitor_name)

    def _on_focus_changed(self, *_):
        self.refresh()

    def _on_monitor_added(self, *_):
        self.refresh()

    def _on_monitor_removed(self, *_):
        self.refresh()


class DisplaysToggle(QSChevronButton):
    """Quick settings tile showing the focused output."""

    def __init__(
        self,
        submenu_factory: Callable[[], QuickSubMenu] | None = None,
        popup=None,
        **kwargs,
    ):
        super().__init__(
            action_icon=_MONITOR_ICON,
            action_title=_("widget.quick_settings.displays.title"),
            action_label=_("widget.quick_settings.displays.unknown"),
            submenu_factory=submenu_factory,
            **kwargs,
        )
        self.popup = popup

        self._handler_ids: list[int] = []
        for event, callback in (
            ("event::focusedmonv2", self._on_focus_changed),
            ("event::monitoraddedv2", self._on_monitors_changed),
            ("event::monitorremoved", self._on_monitors_changed),
        ):
            self._handler_ids.append(hyprland_service.connect(event, callback))
        self.connect("destroy", self._on_destroy)

        # Purely informational tile; the chevron opens the picker.
        self.action_button.set_sensitive(False)
        hyprland_service.on_ready(self.refresh)

    def _on_destroy(self, *_):
        if self._handler_ids:
            for handler_id in self._handler_ids:
                safe_disconnect(hyprland_service, handler_id)
            self._handler_ids = []

    def refresh(self):
        hyprland_service.get_monitors_async(self._on_monitors)

    def _on_monitors(self, monitors):
        if not monitors:
            return
        focused = next(
            (monitor for monitor in monitors if monitor.get("focused", False)), None
        )
        if focused is None:
            return
        self.action_label.set_label(
            focused.get("name") or _("widget.quick_settings.displays.unknown")
        )

    def _on_focus_changed(self, *_):
        self.refresh()

    def _on_monitors_changed(self, *_):
        self.refresh()

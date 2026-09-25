from fabric.hyprland.widgets import HyprlandEvent
from fabric.utils import logger
from fabric.widgets.label import Label

from shared.widget_container import ButtonWidget
from utils.hyprland import hyprland_service
from utils.i18n import _
from utils.widget_utils import nerd_font_icon


class SubMapWidget(ButtonWidget):
    """A widget to display the current submap."""

    def __init__(self, **kwargs):
        super().__init__(name="submap", **kwargs)

        self.submap_label = Label(
            label=_("widget.submap.label"), style_classes="panel-text"
        )

        self.container_box.add(self.submap_label)

        if self.config.get("show_icon", True):
            # Create a TextIcon with the specified icon and size
            self.icon = nerd_font_icon(
                icon=self.config.get("icon"),
                props={"style_classes": ["panel-font-icon"]},
            )
            self.container_box.add(self.icon)

        self._register_handlers(
            hyprland_service,
            {"event::submap": self.on_submap_event},
        )

        # all aboard...
        hyprland_service.on_ready(lambda: self.on_ready(None))

    def on_ready(self, _):
        self._fetch_submap()
        logger.info("[Submap] Connected to the hyprland socket")

    def _update_display(self, submap: str):
        """Update label, visibility, and tooltip with the given submap name."""
        if submap == "unknown request":
            submap = "default"

        self.submap_label.set_label(submap)

        if self.config.get("hide_on_default", False):
            if submap == "default":
                self.hide()
            else:
                self.show()

        self.set_tooltip_if_enabled(_("widget.submap.current", submap=submap))

    def on_submap_event(self, _, event: HyprlandEvent):
        """Handle event::submap — use the event data directly, no extra hyprctl call."""
        if not event.data:
            return
        # event.data is a tuple with the submap name as the first element
        submap = event.data[0] if isinstance(event.data, (list, tuple)) else event.data
        self._update_display(str(submap))

    def _handle_submap_data(self, data, *_):
        if data is None:
            return
        submap = data if isinstance(data, str) else str(data)
        self._update_display(submap)

    def _fetch_submap(self):
        """Send an async hyprctl submap query — used only for initial load."""
        hyprland_service.get_submap_async(self._handle_submap_data)

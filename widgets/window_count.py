from fabric.utils import logger
from fabric.widgets.label import Label

from shared.widget_container import ButtonWidget
from utils.hyprland import hyprland_service


class WindowCountWidget(ButtonWidget):
    """A widget to display windows in active workspace."""

    def __init__(self, **kwargs):
        super().__init__(name="window_count", **kwargs)

        self._service = hyprland_service

        self.count_label = Label(label="0", style_classes="panel-text")
        self.container_box.add(self.count_label)

        self._register_handlers(
            self._service.connection,
            {
                "event::workspace": self._get_window_count,
                "event::focusedmon": self._get_window_count,
                "event::openwindow": self._get_window_count,
                "event::closewindow": self._get_window_count,
                "event::movewindow": self._get_window_count,
            },
        )

        # all aboard...
        self._service.on_ready(lambda: self.on_ready(None))

    def on_ready(self, _):
        self._get_window_count(None, None)
        logger.info("[WindowCount] Connected to the hyprland socket")

    def _handle_workspace_response(self, data, *_):
        try:
            count = data.get("windows", 0)
            label_format = self.config.get("label_format", "[{count}]")
            self.count_label.set_label(label_format.format(count=count))

            ws_id = data.get("id")
            self.set_tooltip_if_enabled(f"Workspace: {ws_id}, Windows: {count}")

            if self.config.get("hide_when_zero", False):
                self.set_visible(count != 0)

            logger.info(f"[WindowCount] Workspace: {data.get('id')} | Windows: {count}")
        except Exception as e:
            logger.exception(f"[WindowCount] Failed to parse workspace data: {e}")

    def _get_window_count(self, *_):
        """Get the number of windows in the active workspace."""
        self._service.get_active_workspace_async(self._handle_workspace_response)

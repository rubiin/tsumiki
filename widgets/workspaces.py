from fabric.core.widgets import WorkspaceButton
from fabric.hyprland.service import HyprlandEvent
from fabric.hyprland.widgets import HyprlandWorkspaces

from shared.widget_container import BoxWidget
from utils.functions import unique_list
from utils.widget_utils import setup_cursor_hover


class WorkSpacesWidget(BoxWidget):
    """A widget to display the current workspaces."""

    def __init__(self, **kwargs):
        super().__init__(name="workspaces", spacing=1, **kwargs)

        self.ignored_ws = {int(x) for x in unique_list(self.config.get("ignored", []))}
        self.icon_map = self.config.get("icon_map", {})
        self.label_format = self.config.get("label_format", "{id}")
        self.workspace_count = self.config.get("count", 8)
        self.hide_unoccupied = self.config.get("hide_unoccupied", True)
        self.show_special = self.config.get("show_special", False)
        self.show_urgent = self.config.get("show_urgent", False)
        self.style = self.config.get("style", "numbered")

        # Create a HyperlandWorkspace widget to manage workspace buttons
        self.children = _HyprlandWorkspaces(
            show_urgent=self.show_urgent,
            name="workspaces_widget",
            style_classes=self.style,
            spacing=4,
            # Create buttons for each workspace if occupied
            buttons=self._filter_workspaces(),
            # Factory function to create buttons for each workspace
            buttons_factory=self._setup_button,
            invert_scroll=self.config.get("reverse_scroll", False),
            empty_scroll=self.config.get("empty_scroll", False),
        )

    def _create_workspace_label(self, ws_id: int) -> str:
        return self.icon_map.get(str(ws_id), self.label_format.format(id=ws_id))

    def _setup_button(self, ws_id: int) -> WorkspaceButton:
        visible = ws_id not in self.ignored_ws and (self.show_special or ws_id >= 0)
        button = WorkspaceButton(
            id=ws_id,
            v_align="center",
            label=self._create_workspace_label(ws_id) if self.style != "pill" else None,
            visible=visible,
        )

        setup_cursor_hover(button)  # fix this , do not use this

        return button

    def _filter_workspaces(self):
        """Filter workspaces based on occupancy."""
        if self.hide_unoccupied:
            return None
        else:
            return [
                self._setup_button(ws_id)
                for ws_id in range(1, self.workspace_count + 1)
                if ws_id not in self.ignored_ws
            ]


class _HyprlandWorkspaces(HyprlandWorkspaces):
    """HyprlandWorkspaces subclass that gates urgent handling on config."""

    def __init__(self, show_urgent: bool = False, **kwargs):
        self._show_urgent = show_urgent
        super().__init__(**kwargs)

    def on_urgent(self, _, event: HyprlandEvent):
        if not self._show_urgent:
            return
        return super().on_urgent(_, event)

from collections.abc import Callable

from fabric.hyprland.widgets import get_hyprland_connection
from fabric.utils import (
    cooldown,
    exec_shell_command_async,
    invoke_repeater,
    remove_handler,
)
from fabric.widgets.scale import Scale

from shared.buttons import QSChevronButton
from shared.submenu import QuickSubMenu
from utils.functions import is_app_running, toggle_command
from utils.i18n import _
from utils.icons import get_text_icon
from utils.widget_utils import (
    create_scale,
)


class HyprSunsetSubMenu(QuickSubMenu):
    """A submenu to display application-specific audio controls."""

    def __init__(self, **kwargs):
        self.scan_button = None

        self._hyprland_connection = get_hyprland_connection()

        self.scale = create_scale(
            name="hyprsunset-scale",
            increments=(100, 100),
            max_value=10000,
            min_value=1000,
            value=2600,
        )

        super().__init__(
            title=_("widget.quick_settings.hyprsunset.title"),
            title_icon=get_text_icon("nightlight.enabled", "󱩌"),
            name="hyprsunset-sub-menu",
            scan_button=self.scan_button,
            child=self.scale,
            **kwargs,
        )

        # Connect the slider immediately
        self.scale.connect("value-changed", self.on_scale_move)
        self._repeater_id = invoke_repeater(1000, self.update_scale)
        # Refresh when first shown; the repeater's initial call may run before
        # mapping, when the visibility gate skips it.
        self.connect("map", self.update_scale)
        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, *_):
        if self._repeater_id is not None:
            remove_handler(self._repeater_id)
            self._repeater_id = None

    @cooldown(0.1)
    def on_scale_move(self, scale: Scale):
        temperature = int(scale.get_value())
        exec_shell_command_async(
            f"hyprctl hyprsunset temperature {temperature}",
            lambda *_: self._update_ui(temperature),
        )
        return True

    def update_scale(self, *_):
        if not self.get_mapped():
            return True
        if is_app_running("hyprsunset"):
            self.scale.set_sensitive(True)
            exec_shell_command_async(
                "hyprctl hyprsunset temperature",
                self._update_ui,
            )
        else:
            self.scale.set_sensitive(False)
        return True

    def _update_ui(self, moved_pos: str | int):
        # Update the scale value based on the current temperature
        if isinstance(moved_pos, str):
            moved_pos = moved_pos.strip().rstrip("kK")
        sanitized_value = int(moved_pos)

        # Avoid unnecessary updates if the value hasn't changed
        if sanitized_value == round(self.scale.get_value()):
            return

        self.scale.set_value(sanitized_value)
        self.scale.set_tooltip_text(f"{sanitized_value}K")


class HyprSunsetToggle(QSChevronButton):
    """A widget to display a toggle button for Wifi."""

    def __init__(
        self,
        submenu_factory: Callable[[], QuickSubMenu] | None = None,
        popup=None,
        **kwargs,
    ):
        super().__init__(
            action_icon=get_text_icon("nightlight.disabled", "󰛨"),
            pixel_size=20,
            action_label=_("widget.quick_settings.hyprsunset.enabled"),
            submenu_factory=submenu_factory,
            **kwargs,
        )

        self.popup = popup
        self.action_button.set_sensitive(True)

        self.connect("action-clicked", self.on_action)

        self._register_repeater(invoke_repeater(1000, self.update_action_button))
        # Refresh when first shown; the repeater's initial call may run before
        # mapping, when the visibility gate skips it.
        self.connect("map", self.update_action_button)

    def on_action(self, *_):
        """Handle the action button click event."""
        submenu = self.ensure_submenu()
        if submenu is None:
            return True
        # Get current slider value for dynamic command
        current_temp = int(submenu.scale.get_value())
        toggle_command("hyprsunset", f"hyprsunset -t {current_temp}")
        if self.popup is not None:
            self.popup.hide_popover()
        return True

    def update_action_button(self, *_args):
        if not self.get_mapped():
            return True

        self.is_running = is_app_running("hyprsunset")

        if self.is_running:
            self.action_icon.set_label(get_text_icon("nightlight.enabled", "󱩌"))
            self.action_label.set_label(_("widget.quick_settings.hyprsunset.enabled"))
            self.set_active_style(True)
        else:
            self.action_icon.set_label(get_text_icon("nightlight.disabled", "󰛨"))
            self.action_label.set_label(_("common.disabled"))
            self.set_active_style(False)
        return True

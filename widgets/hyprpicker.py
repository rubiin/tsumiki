from fabric.utils import Gdk, exec_shell_command_async, os

from shared.widget_container import ButtonWidget
from utils.constants import ASSETS_DIR
from utils.i18n import _


class HyprPickerWidget(ButtonWidget):
    """A widget to pick a color."""

    def __init__(self, **kwargs):
        super().__init__(name="hyprpicker", **kwargs)

        if self.config.get("show_icon", True):
            # Create a TextIcon with the specified icon and size
                    self.add_panel_content(
            self.config.get("icon"),
            _("widget.hyprpicker.label"),
            show_label=self.config.get("label", True),
        )
        self.connect("button-press-event", self.on_button_press)

        self.initialized = False

        self.set_tooltip_if_enabled(_("widget.hyprpicker.tooltip"))

    def lazy_init(self):
        if not self.initialized:
            self.script_file = f"{ASSETS_DIR}/scripts/hyprpicker.sh"
            if not os.path.isfile(self.script_file):
                self.set_sensitive(False)
                self.set_tooltip_text(_("widget.hyprpicker.script_not_found"))
                return
            self.initialized = True

    def on_button_press(self, button, event):
        self.lazy_init()

        if not self.initialized:
            return  # Early exit if script not available

        # A list, not a shell string: the script path is a filesystem path and
        # must not be re-parsed.
        base_command = [self.script_file]
        if self.config.get("quiet", False):
            base_command.append("--no-notify")

        # Mouse event handler
        if event.type == Gdk.EventType.BUTTON_PRESS:
            if event.button == 1:
                # Left click: HEX
                exec_shell_command_async([*base_command, "-hex"])
            elif event.button == 2:
                # Middle click: HSV
                exec_shell_command_async([*base_command, "-hsv"])
            elif event.button == 3:
                # Right click: RGB
                exec_shell_command_async([*base_command, "-rgb"])

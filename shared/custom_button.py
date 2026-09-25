"""Custom button widgets for executing shell commands."""

from fabric.utils import exec_shell_command_async
from fabric.widgets.label import Label

from utils.widget_utils import nerd_font_icon

from .widget_container import ButtonWidget


class CustomButtonWidget(ButtonWidget):
    """A widget that executes a custom bash command when clicked."""

    def __init__(
        self, widget_name: str = "custom_button", config: dict | None = None, **kwargs
    ):
        super().__init__(name=widget_name, **kwargs)

        if config is not None:
            self.config = config

        # Get command from config
        self.command = self.config.get("command", "")

        if not self.command:
            raise ValueError(
                f"Custom button '{widget_name}' requires a 'command' in config"
            )

        # Setup icon if specified
        if self.config.get("show_icon", True):
            icon = self.config.get("icon")
            if icon:
                self.icon = nerd_font_icon(
                    icon=icon,
                    props={"style_classes": ["panel-font-icon"]},
                )
                self.container_box.add(self.icon)

        # Setup label if specified
        if self.config.get("label", True):
            label_text = self.config.get("label_text", "Button")
            self.label = Label(label=label_text, style_classes="panel-text")
            self.container_box.add(self.label)

        # Connect click handler
        self.connect("clicked", self.on_click)

        # Setup tooltip
        self.set_tooltip_if_enabled(
            self.config.get("tooltip_text", f"Execute: {self.command}"),
            default=True,
        )

    def on_click(self, *_):
        """Execute the custom command when button is clicked."""
        if self.command:
            exec_shell_command_async(
                self.command,
                lambda _: None,  # No callback needed
            )

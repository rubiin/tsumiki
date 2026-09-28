from shared.button_toggle import CommandSwitcher


class HyprIdleWidget(CommandSwitcher):
    """A widget to control the hypridle command."""

    def __init__(self, **kwargs):
        super().__init__(
            command="hypridle",
            enabled_icon="",
            disabled_icon="",
            name="hypridle",
            **kwargs,
        )
        # Config is available now that super().__init__() has run.
        self.enabled_icon = self.config.get("enabled_icon", self.enabled_icon)
        self.disabled_icon = self.config.get("disabled_icon", self.disabled_icon)
        self.icon.set_label(self.enabled_icon)
        self.set_tooltip_if_enabled("Control the hypridle command", default=True)

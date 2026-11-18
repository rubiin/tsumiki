from shared.button_toggle import CommandSwitcher


def _command_args(temperature: str, gamma: int) -> str:
    """Build hyprsunset flags, leaving out the default gamma."""
    args = f"-t {temperature}"
    if gamma != 100:
        args += f" -g {gamma}"
    return args


class HyprSunsetWidget(CommandSwitcher):
    """A widget to control the hyprsunset command."""

    def __init__(self, **kwargs):
        super().__init__(
            command="hyprsunset",
            enabled_icon="",
            disabled_icon="",
            name="hyprsunset",
            **kwargs,
        )
        # Config is available now that super().__init__() has run.
        self.enabled_icon = self.config.get("enabled_icon", self.enabled_icon)
        self.disabled_icon = self.config.get("disabled_icon", self.disabled_icon)
        self.refresh_formatted_label(self.enabled_icon)
        self.set_tooltip_if_enabled("Adjust screen temperature", default=True)
        # Pass the configured temperature and gamma to hyprsunset.
        temperature = self.config.get("temperature", "6500")
        gamma = self.config.get("gamma", 100)
        self.full_command = f"hyprsunset {_command_args(temperature, gamma)}"

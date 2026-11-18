from shared.button_toggle import CaffeineSwitcher


class HyprIdleWidget(CaffeineSwitcher):
    """A widget to keep the screen awake through the caffeine idle inhibitor."""

    def __init__(self, **kwargs):
        super().__init__(
            enabled_icon="",
            disabled_icon="",
            name="hypridle",
            **kwargs,
        )
        # Config is available now that super().__init__() has run.
        self.enabled_icon = self.config.get("enabled_icon", self.enabled_icon)
        self.disabled_icon = self.config.get("disabled_icon", self.disabled_icon)

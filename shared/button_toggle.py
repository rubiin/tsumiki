from fabric.utils import logger

import utils.functions as helpers
from services import caffeine_service
from utils.change_cache import ChangeCache
from utils.i18n import _

from .widget_container import ButtonWidget


class CommandSwitcher(ButtonWidget):
    """A button widget to toggle a command; useful for two-state services."""

    def __init__(
        self,
        command: str,
        enabled_icon: str,
        disabled_icon: str,
        name: str,
        label=True,
        args="",
        tooltip=True,
        style_classes="",
        **kwargs,
    ):
        self.command = command
        self.full_command = f"{command} {args}"

        super().__init__(
            name=name,
            **kwargs,
        )

        # A missing binary must not take down the whole bar: raising here
        # would abort every widget laid out after this one.
        self.command_available = True
        try:
            helpers.check_executable_exists(self.command)
        except helpers.ExecutableNotFoundError as e:
            self.command_available = False
            logger.warning(f"[{name}] Command not found: {e}")

        self.add_style_class(style_classes)

        self.enabled_icon = enabled_icon
        self.disabled_icon = disabled_icon
        self.label = label
        self.tooltip = tooltip

        self.label_format = self.config.get("label_format", "{state}")
        self.add_formatted_label(self.label_format, enabled_icon, state="")

        self.connect("clicked", self.on_click)

        # The 1 Hz tick re-applies unchanged state otherwise, and each apply
        # invalidates style or re-renders a label.
        self._changes = ChangeCache()
        self._add_repeater(1000, self._update_ui)
        # The repeater's first call can land before mapping; refresh again on map.
        self.connect("map", self._update_ui)
        self._update_ui()

    def on_click(self, *_args):
        if not self.command_available:
            return True
        helpers.toggle_command(
            self.command,
            full_command=self.full_command,
        )
        self._update_ui()
        return True

    def _update_ui(self, *_args):
        if not self.get_mapped():
            return True

        # Nothing to poll when the binary is absent, and the disabled icon plus a
        # tooltip already say so.
        is_running = (
            helpers.is_app_running(self.command) if self.command_available else False
        )

        self._changes.apply(
            "active", is_running, lambda value: self.toggle_css_class("active", value)
        )

        label = _("common.enabled") if is_running else _("common.disabled")

        icon = self.enabled_icon if is_running else self.disabled_icon
        # Keyed on icon *and* state: hypridle passes one glyph for both states,
        # so an icon-only key would skip the text when just the state flips.
        self._changes.apply(
            "panel",
            (icon, label if self.label else ""),
            lambda value: self.refresh_formatted_label(value[0], state=value[1]),
        )

        if self.tooltip and self.tooltips_enabled:
            if self.command_available:
                tooltip = f"{self.command} {label.lower()}"
            else:
                missing = _("common.not_found", default="not found")
                tooltip = f"{self.command}: {missing}"
            self._changes.apply("tooltip", tooltip, self.set_tooltip_text)

        return True


class CaffeineSwitcher(ButtonWidget):
    """A two-state button backed by the caffeine idle inhibitor service."""

    def __init__(
        self,
        enabled_icon: str,
        disabled_icon: str,
        name: str,
        label=True,
        tooltip=True,
        style_classes="",
        **kwargs,
    ):
        self.service = caffeine_service
        self.switcher_name = name

        super().__init__(
            name=name,
            **kwargs,
        )

        self.add_style_class(style_classes)

        self.enabled_icon = enabled_icon
        self.disabled_icon = disabled_icon
        self.label = label
        self.tooltip = tooltip

        self.label_format = self.config.get("label_format", "{state}")
        self.add_formatted_label(self.label_format, enabled_icon, state="")

        self.connect("clicked", self.on_click)

        self._changes = ChangeCache()
        self._register_handlers(self.service, {"notify::active": self._update_ui})
        self.connect("map", self._update_ui)
        self._update_ui()

    def on_click(self, *_args):
        self.service.active = not self.service.active
        # Re-read instead of assuming the click worked: taking the lock can fail.
        self._update_ui()
        return True

    def _update_ui(self, *_args):
        if not self.get_mapped():
            return True

        active = bool(self.service.active)

        self._changes.apply(
            "active", active, lambda value: self.toggle_css_class("active", value)
        )

        label = _("common.enabled") if active else _("common.disabled")
        icon = self.enabled_icon if active else self.disabled_icon
        self._changes.apply(
            "panel",
            (icon, label if self.label else ""),
            lambda value: self.refresh_formatted_label(value[0], state=value[1]),
        )

        if self.tooltip and self.tooltips_enabled:
            tooltip = f"{self.switcher_name} {label.lower()}"
            self._changes.apply("tooltip", tooltip, self.set_tooltip_text)

        return True

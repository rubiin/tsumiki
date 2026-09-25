import contextlib

from fabric.utils import invoke_repeater

from services import bluetooth_service, notification_service, style_service
from services.network import NetworkService
from shared.button_toggle import CommandSwitcher
from shared.buttons import HoverButton
from utils.i18n import _
from utils.icons import get_text_icon
from widgets.quick_settings.components import QuickSettingsIconLabelRow


def _toggle_row(icon: str, label: str) -> QuickSettingsIconLabelRow:
    """Build the icon+label row for a quick settings toggle card."""
    return QuickSettingsIconLabelRow(
        icon=icon,
        label=label,
        row_classes=["quicksettings-toggle-row"],
        h_align="fill",
    )


class QuickSettingToggler(CommandSwitcher):
    """A button widget to toggle a command."""

    def __init__(
        self,
        command: str,
        name: str,
        enabled_icon: str,
        disabled_icon: str,
        args="",
        **kwargs,
    ):
        super().__init__(
            command,
            enabled_icon,
            disabled_icon,
            name,
            args=args,
            label=True,
            tooltip=False,
            interval=1000,
            style_classes="quicksettings-toggler",
            **kwargs,
        )


class HyprIdleQuickSetting(QuickSettingToggler):
    """A button to toggle the hyper idle mode."""

    def __init__(self, popup, **kwargs):
        super().__init__(
            command="hypridle",
            enabled_icon=get_text_icon("idle.enabled", ""),
            disabled_icon=get_text_icon("idle.disabled", ""),
            name="quicksettings-togglebutton",
            **kwargs,
        )
        self.connect(
            "clicked", lambda *_: popup.hide_popover() if popup is not None else None
        )


class NotificationQuickSetting(HoverButton):
    """A button to toggle the notification."""

    def __init__(self, popup, **kwargs):
        super().__init__(
            name="quicksettings-togglebutton",
            style_classes="quicksettings-toggler",
            **kwargs,
        )

        self.popup = popup

        self.row = _toggle_row(
            get_text_icon("notifications.noisy", "󰂜"),
            _("widget.quick_settings.notifications.noisy"),
        )

        self.notification_icon = self.row.icon
        self.notification_label = self.row.label

        self.children = self.row

        self._register_handlers(
            notification_service,
            {"dnd": self.toggle_notification},
        )

        self.connect("clicked", self.on_click)

        self.toggle_notification(None, notification_service.dont_disturb)

    def on_click(self, *_):
        """Toggle the notification."""
        notification_service.dont_disturb = not notification_service.dont_disturb
        if self.popup is not None:
            self.popup.hide_popover()

    def toggle_notification(self, _sender, value: bool, *_args):
        """Toggle the notification."""

        self.toggle_css_class(
            "active",
            not value,
        )

        if value:
            self.notification_label.set_label(
                _("widget.quick_settings.notifications.quiet")
            )
            self.notification_icon.set_label(get_text_icon("notifications.silent", "󰪑"))

        else:
            self.notification_label.set_label(
                _("widget.quick_settings.notifications.noisy")
            )
            self.notification_icon.set_label(get_text_icon("notifications.noisy", "󰂜"))


def _wifi_device():
    """Return the wifi device if available, else None."""
    try:
        return NetworkService().wifi_device
    except Exception:
        return None


def flight_mode_enabled() -> bool:
    """Return whether flight mode is on (wifi and bluetooth both disabled)."""
    try:
        wifi = _wifi_device()
        wifi_on = bool(wifi and wifi.enabled)
        bluetooth_on = bool(bluetooth_service.enabled)
    except Exception:
        return False
    return not wifi_on and not bluetooth_on


class FlightModeToggle(HoverButton):
    """A button to toggle flight mode."""

    def __init__(self, popup, **kwargs):
        super().__init__(
            name="quicksettings-togglebutton",
            style_classes="quicksettings-toggler",
            **kwargs,
        )

        self.popup = popup

        self.row = _toggle_row(
            get_text_icon("flight.disabled", "󰗔"),
            _("common.disabled"),
        )

        self.flight_icon = self.row.icon
        self.flight_label = self.row.label

        self.children = self.row

        self.connect("clicked", self.on_click)

        self._register_repeater(invoke_repeater(1000, self.update_state))
        # Refresh when first shown; the repeater's initial call may run before
        # mapping, when the visibility gate skips it.
        self.connect("map", self.update_state)

    def on_click(self, *_):
        """Toggle flight mode on/off."""
        turn_on = not flight_mode_enabled()

        # Turn off WiFi and Bluetooth when enabling flight mode.
        wifi = _wifi_device()
        if wifi:
            wifi.enabled = not turn_on
        with contextlib.suppress(Exception):
            bluetooth_service.enabled = not turn_on

        if self.popup is not None:
            self.popup.hide_popover()

        self.update_state()

    def update_state(self, *_args):
        if not self.get_mapped():
            return True

        enabled = flight_mode_enabled()
        self.toggle_css_class("active", enabled)
        self.flight_icon.set_label(
            get_text_icon("flight.enabled" if enabled else "flight.disabled")
        )
        if enabled:
            self.flight_label.set_label(_("common.enabled"))
        else:
            self.flight_label.set_label(_("common.disabled"))
        return True


class DarkModeToggle(HoverButton):
    """A button to toggle between dark and light mode."""

    def __init__(self, popup, **kwargs):
        super().__init__(
            name="quicksettings-togglebutton",
            style_classes="quicksettings-toggler",
            **kwargs,
        )

        self.popup = popup

        self.row = _toggle_row(
            get_text_icon("color.dark", "󰖔"), _("widget.quick_settings.dark_mode.dark")
        )

        self.mode_icon = self.row.icon
        self.mode_label = self.row.label

        self.children = self.row

        self._register_handlers(
            style_service,
            {"theme_changed": self.update_state},
        )

        self.connect("clicked", self.on_click)

        self.update_state()

    def on_click(self, *_):
        """Toggle between dark and light mode."""
        new_mode = "light" if style_service.mode == "dark" else "dark"
        style_service.set_mode(new_mode)
        if self.popup is not None:
            self.popup.hide_popover()

    def update_state(self, *_args):
        dark = style_service.mode == "dark"
        self.toggle_css_class("active", dark)
        self.mode_icon.set_label(get_text_icon("color.dark" if dark else "color.light"))
        if dark:
            self.mode_label.set_label(_("widget.quick_settings.dark_mode.dark"))
        else:
            self.mode_label.set_label(_("widget.quick_settings.dark_mode.light"))

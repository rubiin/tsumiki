import contextlib

from fabric.utils import invoke_repeater

from services import (
    bluetooth_service,
    caffeine_service,
    notification_service,
    recorder_service,
    style_service,
)
from services.network import NetworkService
from utils.config import tsumiki_config
from utils.i18n import _
from utils.icons import get_text_icon
from widgets.quick_settings.toggle_base import QuickSettingToggle


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


class HyprIdleQuickSetting(QuickSettingToggle):
    """A button to keep the screen awake through the caffeine idle inhibitor."""

    def __init__(self, popup, **kwargs):
        super().__init__(
            popup,
            icon=get_text_icon("idle.enabled", ""),
            title=_("widget.quick_settings.caffeine.title"),
            subtitle=_("common.off"),
            **kwargs,
        )
        self.service = caffeine_service

        self.caffeine_icon = self.icon_label
        self.caffeine_status = self.status_label

        self._register_handlers(caffeine_service, {"notify::active": self.update_state})
        self.connect("clicked", self.on_click)
        self.connect("map", self.update_state)
        self.update_state()

    def on_click(self, *_):
        """Toggle the caffeine idle inhibitor."""
        caffeine_service.active = not caffeine_service.active
        self.update_state()
        if self.popup is not None:
            self.popup.hide_popover()

    def update_state(self, *_args):
        active = bool(caffeine_service.active)
        self.toggle_css_class("active", active)
        self.caffeine_icon.set_label(
            get_text_icon("idle.enabled" if active else "idle.disabled")
        )
        self.caffeine_status.set_label(
            _("widget.quick_settings.caffeine.awake") if active else _("common.off")
        )


class NotificationQuickSetting(QuickSettingToggle):
    """A button to toggle the notification."""

    def __init__(self, popup, **kwargs):
        super().__init__(
            popup,
            icon=get_text_icon("notifications.noisy", "󰂜"),
            title=_("widget.quick_settings.notifications.title"),
            subtitle=_("common.off"),
            **kwargs,
        )
        self.service = notification_service

        self.notification_icon = self.icon_label
        self.notification_status = self.status_label

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
        self.toggle_css_class("active", not value)

        if value:
            self.notification_status.set_label(_("common.on"))
            self.notification_icon.set_label(get_text_icon("notifications.silent", "󰪑"))
        else:
            self.notification_status.set_label(_("common.off"))
            self.notification_icon.set_label(get_text_icon("notifications.noisy", "󰂜"))


class FlightModeToggle(QuickSettingToggle):
    """A button to toggle flight mode."""

    def __init__(self, popup, **kwargs):
        super().__init__(
            popup,
            icon=get_text_icon("flight.disabled", "󰗔"),
            title=_("widget.quick_settings.flightmode.title"),
            subtitle=_("common.off"),
            **kwargs,
        )

        self._register_repeater(invoke_repeater(1000, self.update_state))
        # The repeater's first call can land before mapping, when the gate skips it.
        self.connect("map", self.update_state)
        self.connect("clicked", self.on_click)

        self.update_state()

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
        self.status_label.set_label(_("common.on") if enabled else _("common.off"))
        return True


class ScreenshotQuickSetting(QuickSettingToggle):
    """A button to take a screenshot."""

    def __init__(self, popup, config=None, **kwargs):
        super().__init__(
            popup,
            icon=get_text_icon("screenshot", "󰆈"),
            title=_("widget.quick_settings.screenshot.label"),
            subtitle=_("widget.quick_settings.screenshot.hint"),
            **kwargs,
        )

        self.config = tsumiki_config.get("widgets", {}).get("screenshot", {})

    def on_click(self, *_):
        """Take a screenshot."""
        recorder_service.screenshot(config=self.config)
        if self.popup is not None:
            self.popup.hide_popover()


class RecorderQuickSetting(QuickSettingToggle):
    """A button to toggle screen recording."""

    def __init__(self, popup, **kwargs):
        super().__init__(
            popup,
            icon=get_text_icon("recorder", "󰻂"),
            title=_("widget.quick_settings.recording.title"),
            subtitle=_("widget.quick_settings.recording.idle"),
            **kwargs,
        )

        self.config = tsumiki_config.get("widgets", {}).get("recorder", {})

        self._register_handlers(recorder_service, {"recording": self.update_state})
        self.connect("clicked", self.on_click)
        self.update_state()

    def on_click(self, *_):
        """Start or stop recording."""
        if recorder_service.is_recording:
            recorder_service.screenrecord_stop()
        else:
            recorder_service.screenrecord_start(config=self.config)
        if self.popup is not None:
            self.popup.hide_popover()

    def update_state(self, *_args):
        recording = recorder_service.is_recording
        self.toggle_css_class("active", recording)
        self.icon_label.set_label(get_text_icon("recorder", "󰻂"))
        if recording:
            self.status_label.set_label(_("widget.quick_settings.recording.recording"))
        else:
            self.status_label.set_label(_("widget.quick_settings.recording.idle"))


class DarkModeToggle(QuickSettingToggle):
    """A button to toggle between dark and light mode."""

    def __init__(self, popup, **kwargs):
        super().__init__(
            popup,
            icon=get_text_icon("color.dark", "󰖔"),
            title=_("widget.quick_settings.dark_mode.title"),
            subtitle=_("common.off"),
            **kwargs,
        )

        self._register_handlers(style_service, {"theme_changed": self.update_state})
        self.connect("clicked", self.on_click)
        self.update_state()

    def on_click(self, *_):
        """Toggle between dark and light mode."""
        new_mode = "light" if style_service.mode == "dark" else "dark"
        style_service.set_mode(new_mode)
        if self.popup is not None:
            self.popup.hide_popover()

    def update_state(self, *_args):
        light = style_service.mode != "dark"
        self.toggle_css_class("active", light)
        self.icon_label.set_label(
            get_text_icon("color.light" if light else "color.dark")
        )
        self.status_label.set_label(_("common.on") if light else _("common.off"))


__all__ = [
    "DarkModeToggle",
    "FlightModeToggle",
    "HyprIdleQuickSetting",
    "NotificationQuickSetting",
    "RecorderQuickSetting",
    "ScreenshotQuickSetting",
]

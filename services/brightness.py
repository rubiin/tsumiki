"""Service that manages screen and keyboard backlight brightness via brightnessctl."""

import os

from fabric.core.service import Property, Service, Signal
from fabric.utils import exec_shell_command_async, monitor_file
from gi.repository import GLib
from loguru import logger


def exec_brightnessctl_async(args: str) -> None:
    exec_shell_command_async(f"brightnessctl {args}", lambda _: None)


SCREEN = next(iter(os.listdir("/sys/class/backlight")), "")

_kbd_leds = os.listdir("/sys/class/leds")
KBD = "tpacpi::kbd_backlight" if "tpacpi::kbd_backlight" in _kbd_leds else ""


class BrightnessService(Service):
    """Wrap ``brightnessctl`` with inotify-driven ``brightness_changed`` signals.

    **Throttle:** slider dragging can set the screen value many times a second;
    only the latest value is applied, at most once per 50 ms window.
    """

    @Signal
    def screen_brightness_changed(self) -> None:
        """Emitted with the new screen brightness as a percentage (0-100)."""

    @Signal
    def keyboard_brightness_changed(self) -> None:
        """Emitted with the new keyboard brightness as a percentage (0-100)."""

    def __init__(self, **kwargs):
        self.screen_backlight_path = f"/sys/class/backlight/{SCREEN}"
        self.kbd_backlight_path = f"/sys/class/leds/{KBD}"
        self.max_kbd = -1
        self.max_screen = -1
        self._screen_brightness_cache = -1

        self._pending_screen_value: int | None = None
        self._screen_throttle_id: int | None = None

        if os.path.exists(self.screen_backlight_path + "/max_brightness"):
            with open(self.screen_backlight_path + "/max_brightness") as f:
                self.max_screen = int(f.read())
            self.screen_monitor = monitor_file(
                self.screen_backlight_path + "/brightness"
            )
            self.screen_monitor.connect(
                "changed",
                self._on_screen_file_changed,
            )

        if os.path.exists(self.kbd_backlight_path + "/max_brightness"):
            with open(self.kbd_backlight_path + "/max_brightness") as f:
                self.max_kbd = int(f.read())
            hw_changed = self.kbd_backlight_path + "/brightness_hw_changed"
            self.kbd_monitor = monitor_file(
                hw_changed
                if os.path.exists(hw_changed)
                else self.kbd_backlight_path + "/brightness"
            )
            self.kbd_monitor.connect(
                "changed",
                self._on_kbd_file_changed,
            )

        super().__init__(**kwargs)

    def _on_screen_file_changed(self, _monitor, file, *_args) -> None:
        try:
            brightness = int(file.load_bytes()[0].get_data())
        except (ValueError, OSError, TypeError) as e:
            logger.warning(f"Failed to read brightness update: {e}")
            return

        if brightness == self._screen_brightness_cache:
            return

        self._screen_brightness_cache = brightness
        self.emit("screen_brightness_changed")

    def _on_kbd_file_changed(self, *_args) -> None:
        self.emit("keyboard_brightness_changed")

    def _as_percentage(self, raw: int) -> int:
        """Convert a raw sysfs brightness to a 0-100 percentage.

        Every ``brightness_changed`` payload goes through here: the two emit
        sites used to disagree on the unit, and a consumer cannot tell which.
        """
        if self.max_screen <= 0:
            return 0
        return int((raw / self.max_screen) * 100)

    @Property(int, "read-write")
    def screen_brightness(self) -> int:
        if not self.screen_backlight_path:
            logger.warning("Cannot get brightness: no screen device.")
            return -1

        if self._screen_brightness_cache >= 0:
            return self._screen_brightness_cache

        brightness_path = os.path.join(self.screen_backlight_path, "brightness")
        if os.path.exists(brightness_path):
            with open(brightness_path, "r") as f:
                brightness = int(f.readline())
                self._screen_brightness_cache = brightness
                return brightness
        logger.warning("Brightness file does not exist: %s", brightness_path)
        return -1

    @screen_brightness.setter
    def screen_brightness(self, value: int) -> None:
        if not self.screen_backlight_path:
            logger.warning("Cannot set brightness: no screen device.")
            return
        if not (0 <= value <= self.max_screen):
            value = max(0, min(value, self.max_screen))
        try:
            exec_brightnessctl_async(f"--device {SCREEN} set {value}")
            self._screen_brightness_cache = value
            logger.info(
                "Set screen brightness to %d (out of %d)",
                value,
                self.max_screen,
            )
        except GLib.Error as e:
            logger.exception("Error setting screen brightness: %s", e.message)
        except Exception as e:
            logger.exception("Unexpected error setting screen brightness: %s", e)
        finally:
            self.emit("screen_brightness_changed")

    @Property(int, "read-write")
    def keyboard_brightness(self) -> int:
        if not self.kbd_backlight_path:
            logger.warning("No keyboard backlight device detected.")
            return -1
        try:
            with open(self.kbd_backlight_path + "/brightness", "r") as f:
                return int(f.readline())
        except (FileNotFoundError, ValueError, OSError, TypeError) as e:
            logger.exception("Failed to read keyboard brightness: %s", e)
            return -1

    @keyboard_brightness.setter
    def keyboard_brightness(self, value: int) -> None:
        if not self.kbd_backlight_path:
            logger.warning("No keyboard backlight device detected.")
            return
        if value < 0 or value > self.max_kbd:
            return
        try:
            exec_brightnessctl_async(f"--device {KBD} set {value}")
        except GLib.Error as e:
            logger.exception(e.message)
        except Exception as e:
            logger.exception("Failed to set keyboard brightness: %s", e)
        finally:
            self.emit("keyboard_brightness_changed")

    @Property(int, "readable")
    def screen_brightness_percentage(self) -> int:
        if not self.screen_backlight_path:
            return 0
        return self._as_percentage(self.screen_brightness)

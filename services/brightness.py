from fabric.core.service import Property, Signal
from fabric.utils import GLib, exec_shell_command_async, logger, monitor_file, os

import utils.functions as helpers
from utils.colors import Colors

from .base import SingletonService


def exec_brightnessctl_async(*args: str) -> None:
    """Run brightnessctl with argv, so no argument needs shell quoting."""
    exec_shell_command_async(["brightnessctl", *args])


class BrightnessService(SingletonService):
    """Service to manage screen brightness levels."""

    @Signal
    def brightness_changed(self, value: int) -> None:
        """Signal emitted when screen brightness changes."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        helpers.check_executable_exists("brightnessctl")
        self._screen_brightness_cache = -1

        # Discover screen backlight device
        try:
            screen_device_list = os.listdir("/sys/class/backlight")
            self.screen_device = screen_device_list[0] if screen_device_list else ""
        except FileNotFoundError:
            logger.exception(f"{Colors.ERROR}No backlight devices found")
            self.screen_device = ""

        if self.screen_device == "":
            logger.warning(f"{Colors.WARNING}No screen backlight device detected.")
            self.screen_backlight_path = ""
            self.max_screen = 0
            self.screen_monitor = None
        else:
            self.screen_backlight_path = f"/sys/class/backlight/{self.screen_device}"
            self.max_screen = self._read_max_brightness(self.screen_backlight_path)

            self.screen_monitor = monitor_file(
                f"{self.screen_backlight_path}/brightness"
            )

            self.screen_monitor.connect(
                "changed",
                self._on_screen_brightness_file_changed,
            )
            # Prime the cache so an unchanged first event (e.g. a driver
            # restoring the same value after resume) stays silent.
            _ = self.screen_brightness

            logger.info(
                f"{Colors.INFO}Brightness service initialized for device: "
                f"{self.screen_device}"
            )

        # Discover keyboard backlight device
        try:
            kbd_list = os.listdir("/sys/class/leds")
            kbd_filtered = [x for x in kbd_list if "kbd_backlight" in x]
            self.kbd = kbd_filtered[0] if kbd_filtered else ""
        except FileNotFoundError:
            logger.exception(f"{Colors.ERROR}No keyboard backlight devices found")
            self.kbd = ""

        self.kbd_backlight_path = f"/sys/class/leds/{self.kbd}" if self.kbd else ""
        self.max_kbd = self._read_max_brightness(self.kbd_backlight_path)

    def _on_screen_brightness_file_changed(self, _, file, *args):
        try:
            brightness = int(file.load_bytes()[0].get_data())
        except (ValueError, OSError, TypeError) as e:
            logger.warning(f"{Colors.WARNING}Failed to read brightness update: {e}")
            return

        if brightness == self._screen_brightness_cache:
            return

        self._screen_brightness_cache = brightness
        self.emit("brightness_changed", brightness)

    def _read_max_brightness(self, path: str) -> int:
        max_brightness_path = os.path.join(path, "max_brightness")
        if os.path.exists(max_brightness_path):
            with open(max_brightness_path, "r") as f:
                return int(f.readline())
        return -1

    @Property(int, "read-write")
    def screen_brightness(self) -> int:
        if not self.screen_backlight_path:
            logger.warning(f"{Colors.WARNING}Cannot get brightness: no screen device.")
            return -1

        if self._screen_brightness_cache >= 0:
            return self._screen_brightness_cache

        brightness_path = os.path.join(self.screen_backlight_path, "brightness")
        if os.path.exists(brightness_path):
            with open(brightness_path, "r") as f:
                brightness = int(f.readline())
                self._screen_brightness_cache = brightness
                return brightness
        logger.warning(
            f"{Colors.WARNING}Brightness file does not exist: {brightness_path}"
        )
        return -1

    @screen_brightness.setter
    def screen_brightness(self, value: int):
        if not self.screen_backlight_path:
            logger.warning(f"{Colors.WARNING}Cannot set brightness: no screen device.")
            return
        if not (0 <= value <= self.max_screen):
            value = max(0, min(value, self.max_screen))
        try:
            exec_brightnessctl_async("--device", self.screen_device, "set", str(value))
            self._screen_brightness_cache = value
            percentage = (
                int((value / self.max_screen) * 100) if self.max_screen > 0 else 0
            )
            self.emit("brightness_changed", percentage)
            logger.info(
                f"{Colors.INFO}Set screen brightness to {value} "
                f"(out of {self.max_screen})"
            )
        except GLib.Error as e:
            logger.exception(
                f"{Colors.ERROR}Error setting screen brightness: {e.message}"
            )
        except Exception as e:
            logger.exception(f"Unexpected error setting screen brightness: {e}")

    @Property(int, "read-write")
    def keyboard_brightness(self) -> int:  # type: ignore
        if not self.kbd_backlight_path:
            logger.warning(f"{Colors.WARNING}No keyboard backlight device detected.")
            return -1
        try:
            with open(self.kbd_backlight_path + "/brightness", "r") as f:
                return int(f.readline())
        except (FileNotFoundError, ValueError, OSError, TypeError) as e:
            logger.exception(f"{Colors.ERROR}Failed to read keyboard brightness: {e}")
            return -1

    @keyboard_brightness.setter
    def keyboard_brightness(self, value: int):
        if not self.kbd_backlight_path:
            logger.warning(f"{Colors.WARNING}No keyboard backlight device detected.")
            return
        if value < 0 or value > self.max_kbd:
            return
        try:
            exec_brightnessctl_async("--device", self.kbd, "set", str(value))
        except GLib.Error as e:
            logger.exception(e.message)
        except Exception as e:
            logger.exception(f"{Colors.ERROR}Failed to set keyboard brightness: {e}")

    @Property(int, "readable")
    def screen_brightness_percentage(self):
        if not self.screen_backlight_path or self.max_screen <= 0:
            return 0
        current_brightness = self.screen_brightness
        return int((current_brightness / self.max_screen) * 100)

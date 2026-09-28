import unittest
from unittest import mock

from services.brightness import BrightnessService


class _StubBytes:
    def __init__(self, payload: bytes):
        self._payload = payload

    def get_data(self) -> bytes:
        return self._payload


class _StubFile:
    """Duck-typed stand-in for Gio.File as read by the change handler."""

    def __init__(self, payload: bytes):
        self._payload = payload

    def load_bytes(self) -> list:
        return [_StubBytes(self._payload)]


def _make_service(cache: int, max_screen: int = 400) -> BrightnessService:
    # Bypass __init__: it binds real /sys devices and spawns file monitors.
    service = BrightnessService.__new__(BrightnessService)
    service._screen_brightness_cache = cache
    service.max_screen = max_screen
    service.screen_device = "intel_backlight"
    service.screen_backlight_path = "/sys/class/backlight/intel_backlight"
    service.emit = mock.Mock()
    return service


class ScreenBrightnessHandlerTest(unittest.TestCase):
    """The file-change handler must suppress unchanged brightness values."""

    def test_changed_value_emits_and_updates_cache(self):
        service = _make_service(cache=100)

        service._on_screen_brightness_file_changed(None, _StubFile(b"150"))

        service.emit.assert_called_once_with("brightness_changed", 37)
        self.assertEqual(service._screen_brightness_cache, 150)

    def test_same_value_is_silent(self):
        service = _make_service(cache=150)

        service._on_screen_brightness_file_changed(None, _StubFile(b"150"))

        service.emit.assert_not_called()
        self.assertEqual(service._screen_brightness_cache, 150)

    def test_unreadable_value_is_silent(self):
        service = _make_service(cache=100)

        service._on_screen_brightness_file_changed(None, _StubFile(b"not-a-number"))

        service.emit.assert_not_called()
        self.assertEqual(service._screen_brightness_cache, 100)


class BrightnessUnitTest(unittest.TestCase):
    """Both emit sites used to disagree: one raw sysfs value, one a percentage.

    Consumers cannot tell which they got, so the signal carries a percentage
    from every path.
    """

    def test_the_setter_and_the_file_monitor_agree(self):
        # The property descriptor needs a GObject-initialised instance, which
        # __new__ does not give us, so drive the setter function directly.
        set_brightness = BrightnessService.screen_brightness.fset
        with mock.patch("services.brightness.exec_brightnessctl_async") as run:
            setter = _make_service(cache=0)
            set_brightness(setter, 150)
            emitted_by_setter = setter.emit.call_args[0][1]

            monitor = _make_service(cache=0)
            monitor._on_screen_brightness_file_changed(None, _StubFile(b"150"))
            emitted_by_monitor = monitor.emit.call_args[0][1]

        run.assert_called_once()
        self.assertEqual(emitted_by_setter, 37)
        self.assertEqual(emitted_by_setter, emitted_by_monitor)

    def test_the_percentage_property_uses_the_same_scale(self):
        service = _make_service(cache=150)

        self.assertEqual(service.screen_brightness_percentage, 37)

    def test_an_unknown_maximum_reports_zero_rather_than_dividing(self):
        service = _make_service(cache=150, max_screen=0)

        self.assertEqual(service._as_percentage(150), 0)


if __name__ == "__main__":
    unittest.main()

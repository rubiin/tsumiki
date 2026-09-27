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


def _make_service(cache: int) -> BrightnessService:
    # Bypass __init__: it binds real /sys devices and spawns file monitors.
    service = BrightnessService.__new__(BrightnessService)
    service._screen_brightness_cache = cache
    service.emit = mock.Mock()
    return service


class ScreenBrightnessHandlerTest(unittest.TestCase):
    """The file-change handler must suppress unchanged brightness values."""

    def test_changed_value_emits_and_updates_cache(self):
        service = _make_service(cache=100)

        service._on_screen_brightness_file_changed(None, _StubFile(b"150"))

        service.emit.assert_called_once_with("brightness_changed", 150)
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


if __name__ == "__main__":
    unittest.main()

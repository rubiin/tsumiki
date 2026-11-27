"""Tests for the WiFi service's access-point rebuild coalescing.

Each ``changed`` makes every listener re-read ``access_points``, which decodes,
dedups and sorts every AP, so a burst of per-AP signals must cost one rebuild.
"""

import unittest
from unittest import mock

try:
    import gi

    gi.require_version("NM", "1.0")
    from services.network import Wifi

    HAS_NM = True
except (ImportError, ValueError):  # NetworkManager bindings unavailable
    HAS_NM = False


class _FakeGObject:
    """Duck-typed stand-in for NM.Client / NM.DeviceWifi signal sources."""

    def __init__(self):
        self.handlers: dict[str, list] = {}
        self._handlers_by_id: dict[int, tuple[str, object]] = {}
        self._next_handler_id = 0

    def connect(self, signal, callback):
        self._next_handler_id += 1
        self.handlers.setdefault(signal, []).append(callback)
        self._handlers_by_id[self._next_handler_id] = (signal, callback)
        return self._next_handler_id

    def disconnect(self, handler_id):
        signal, callback = self._handlers_by_id.pop(handler_id, (None, None))
        if callback is not None and callback in self.handlers.get(signal, []):
            self.handlers[signal].remove(callback)

    def fire(self, signal, *args):
        for callback in list(self.handlers.get(signal, [])):
            callback(self, *args)

    def get_active_access_point(self):
        return None


class _FakeGLib:
    """Holds one-shot timers until the test decides to run them."""

    Error = RuntimeError

    def __init__(self):
        self.timers: dict[int, tuple[int, object]] = {}
        self._next_id = 0

    def timeout_add(self, delay_ms, callback):
        self._next_id += 1
        self.timers[self._next_id] = (delay_ms, callback)
        return self._next_id

    def source_remove(self, source_id):
        self.timers.pop(source_id, None)

    def run_pending(self) -> int:
        pending = list(self.timers.values())
        self.timers.clear()
        for _delay_ms, callback in pending:
            callback()
        return len(pending)


@unittest.skipUnless(HAS_NM, "NetworkManager bindings unavailable")
class WifiApUpdateCoalescingTest(unittest.TestCase):
    """A burst of AP signals must cost one list rebuild, not one per signal."""

    def setUp(self):
        self.client = _FakeGObject()
        self.device = _FakeGObject()
        self.glib = _FakeGLib()
        # replace_timeout (used for coalescing) lives in utils.decorators.
        for target in ("utils.decorators.GLib", "services.network.GLib"):
            patcher = mock.patch(target, self.glib)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.wifi = Wifi(self.client, self.device)
        self.rebuilds: list = []
        self.wifi.connect("changed", lambda *_: self.rebuilds.append(True))

    def test_a_thirty_network_scan_costs_one_rebuild(self):
        for _ in range(30):
            self.device.fire("access-point-added")

        self.assertEqual(1, len(self.glib.timers), "burst should share one timer")
        self.glib.run_pending()

        self.assertEqual(1, len(self.rebuilds))

    def test_a_removal_burst_also_costs_one_rebuild(self):
        for _ in range(10):
            self.device.fire("access-point-removed")

        self.glib.run_pending()

        self.assertEqual(1, len(self.rebuilds))

    def test_no_rebuild_before_the_timer_fires(self):
        self.device.fire("state-changed")

        self.assertEqual([], self.rebuilds)

    def test_a_later_burst_schedules_a_fresh_rebuild(self):
        self.device.fire("access-point-added")
        self.glib.run_pending()

        self.device.fire("access-point-added")
        self.glib.run_pending()

        self.assertEqual(2, len(self.rebuilds))

    def test_an_ap_strength_change_is_coalesced_too(self):
        ap = _FakeGObject()
        self.device.get_active_access_point = lambda: ap
        self.wifi._activate_ap()

        for _ in range(20):
            ap.fire("notify::strength")

        self.glib.run_pending()

        self.assertEqual(1, len(self.rebuilds))

    def test_a_scan_announcing_nothing_still_refreshes_once(self):
        callbacks: dict = {}

        def _request_scan(_cancellable, callback):
            callbacks["callback"] = callback

        self.device.request_scan_async = _request_scan
        self.device.request_scan_finish = lambda _result: None

        self.wifi.scan()
        callbacks["callback"](self.device, mock.Mock())

        self.glib.run_pending()

        self.assertEqual(1, len(self.rebuilds))

    def test_switching_active_access_point_refreshes_once(self):
        first_ap = _FakeGObject()
        second_ap = _FakeGObject()
        self.device.get_active_access_point = lambda: first_ap
        self.device.fire("notify::active-access-point")
        self.glib.run_pending()
        self.rebuilds.clear()

        self.device.get_active_access_point = lambda: second_ap
        self.device.fire("notify::active-access-point")

        self.assertEqual(1, len(self.glib.timers), "roam should schedule one rebuild")
        self.glib.run_pending()

        self.assertEqual(1, len(self.rebuilds))
        self.assertIs(second_ap, self.wifi._ap)

    def test_losing_the_active_access_point_refreshes(self):
        self.device.get_active_access_point = lambda: _FakeGObject()
        self.device.fire("notify::active-access-point")
        self.glib.run_pending()
        self.rebuilds.clear()

        self.device.get_active_access_point = lambda: None
        self.device.fire("notify::active-access-point")
        self.glib.run_pending()

        self.assertEqual(1, len(self.rebuilds))
        self.assertIsNone(self.wifi._ap)

    def test_the_rebuild_notifies_every_rendered_property(self):
        self.device.fire("access-point-added")
        self.glib.run_pending()

        notified: list[str] = []
        self.wifi.connect("notify", lambda _obj, pspec: notified.append(pspec.name))
        self.wifi.ap_update()

        for prop in ("enabled", "internet", "strength", "ssid", "access-points"):
            self.assertIn(prop, notified)


class WifiIsActiveApTest(unittest.TestCase):
    """The active row is matched by BSSID/path, with SSID as a fallback."""

    def setUp(self):
        self.wifi = Wifi(_FakeGObject(), _FakeGObject())

        self.active = mock.Mock()
        self.active.get_bssid.return_value = "AA:BB:CC:DD:EE:FF"
        self.active.get_path.return_value = (
            "/org/freedesktop/NetworkManager/AccessPoint/1"
        )
        self.active.get_ssid.return_value = mock.Mock(get_data=lambda: b"Home")
        self.wifi._ap = self.active

    def entry(self, bssid="AA:BB:CC:DD:EE:FF", ssid="Home", path=None):
        return {"bssid": bssid, "ssid": ssid, "path": path}

    def test_matching_bssid_is_active(self):
        self.assertTrue(self.wifi.is_active_ap(self.entry()))

    def test_matching_path_is_active(self):
        path = self.active.get_path.return_value
        self.assertTrue(
            self.wifi.is_active_ap(
                self.entry(bssid="11:22:33:44:55:66", ssid="Other", path=path)
            )
        )

    def test_sibling_bssid_with_the_same_ssid_is_active(self):
        # One SSID on 2.4/5 GHz: the list keeps the strongest, not the joined BSSID.
        self.assertTrue(self.wifi.is_active_ap(self.entry(bssid="11:22:33:44:55:66")))

    def test_a_different_ssid_is_not_active(self):
        self.assertFalse(
            self.wifi.is_active_ap(self.entry(bssid="11:22:33:44:55:66", ssid="Guest"))
        )

    def test_a_bssid_string_still_works(self):
        self.assertTrue(self.wifi.is_active_ap("AA:BB:CC:DD:EE:FF"))
        self.assertFalse(self.wifi.is_active_ap("11:22:33:44:55:66"))

    def test_no_active_access_point_matches_nothing(self):
        self.wifi._ap = None
        self.assertFalse(self.wifi.is_active_ap(self.entry()))
        self.assertFalse(self.wifi.is_active_ap("AA:BB:CC:DD:EE:FF"))


if __name__ == "__main__":
    unittest.main()

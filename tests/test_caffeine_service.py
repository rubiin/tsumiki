"""Tests for the caffeine idle-inhibitor service."""

import unittest
from unittest import mock

from gi.repository import GLib

import services.caffeine as caffeine
from services.caffeine import Caffeine, _get_logind_proxy, _idle_inhibitor_active


def _reply(inhibitors: list[tuple]):
    reply = mock.Mock()
    reply.unpack.return_value = (inhibitors,)
    return reply


def _proxy(reply):
    proxy = mock.Mock()
    proxy.call_sync.return_value = reply
    return proxy


class IdleInhibitorActiveTest(unittest.TestCase):
    """The service reports awake when logind already holds an idle lock."""

    def _call(self, inhibitors):
        with mock.patch(
            "services.caffeine._get_logind_proxy",
            return_value=_proxy(_reply(inhibitors)),
        ):
            return _idle_inhibitor_active()

    def test_blocking_idle_inhibitor_is_active(self):
        inhibitors = [("idle:sleep", "Fabric", "Caffeine is on", "block", 1000, 42)]

        self.assertTrue(self._call(inhibitors))

    def test_delay_inhibitor_is_ignored(self):
        inhibitors = [("idle", "someone", "countdown", "delay", 1000, 42)]

        self.assertFalse(self._call(inhibitors))

    def test_unrelated_inhibitor_is_ignored(self):
        inhibitors = [("sleep", "someone", "keep awake", "block", 1000, 42)]

        self.assertFalse(self._call(inhibitors))

    def test_no_inhibitors_is_inactive(self):
        self.assertFalse(self._call([]))


class RestoreStateTest(unittest.TestCase):
    """Init must pick up an idle lock taken by another process."""

    def _service(self) -> Caffeine:
        service = Caffeine.__new__(Caffeine)
        service._fd = None
        service._external = False
        service.notify = mock.Mock()
        return service

    def test_existing_lock_sets_active(self):
        service = self._service()

        with mock.patch("services.caffeine._idle_inhibitor_active", return_value=True):
            service._restore_state()

        self.assertTrue(service.active)
        service.notify.assert_called_once_with("active")

    def test_no_lock_stays_inactive(self):
        service = self._service()

        with mock.patch("services.caffeine._idle_inhibitor_active", return_value=False):
            service._restore_state()

        self.assertFalse(service.active)
        service.notify.assert_not_called()

    def test_turning_off_external_lock_does_not_close_a_fd(self):
        service = self._service()
        service._external = True

        with mock.patch("services.caffeine.os.close") as close:
            Caffeine.active.fset(service, False)

        close.assert_not_called()
        self.assertFalse(service.active)


class LogindProxyTest(unittest.TestCase):
    """One proxy is reused for every logind call."""

    def setUp(self):
        self._saved = caffeine._LOGIND_PROXY
        caffeine._LOGIND_PROXY = None
        self.addCleanup(lambda: setattr(caffeine, "_LOGIND_PROXY", self._saved))

    def test_proxy_is_created_once(self):
        proxy = mock.Mock()

        with mock.patch(
            "services.caffeine.Gio.DBusProxy.new_sync", return_value=proxy
        ) as new_sync:
            self.assertIs(_get_logind_proxy(), proxy)
            self.assertIs(_get_logind_proxy(), proxy)

        new_sync.assert_called_once()

    def test_connection_failure_returns_none(self):
        error = GLib.Error("system bus unavailable")

        with mock.patch("services.caffeine.Gio.DBusProxy.new_sync", side_effect=error):
            self.assertIsNone(_get_logind_proxy())


class TakeLockErrorTest(unittest.TestCase):
    """A failed D-Bus call reads as inactive instead of raising."""

    def test_dbus_error_is_inactive(self):
        error = GLib.Error("system bus unavailable")
        proxy = mock.Mock()
        proxy.call_sync.side_effect = error

        with mock.patch("services.caffeine._get_logind_proxy", return_value=proxy):
            self.assertFalse(_idle_inhibitor_active())

    def test_missing_proxy_is_inactive(self):
        with mock.patch("services.caffeine._get_logind_proxy", return_value=None):
            self.assertFalse(_idle_inhibitor_active())

"""
Caffeine: keeps the screen from idling (dimming, locking, sleeping).

While on, it holds a logind "idle" inhibitor lock, which hypridle honours. The
lock is a file descriptor: closing it releases the lock, and so does fabric
exiting or crashing, so the screen can never be left awake by accident.
"""

import os

from fabric.core.service import Property
from gi.repository import Gio, GLib
from loguru import logger

from services.base import SingletonService

_LOGIND_PROXY: Gio.DBusProxy | None = None


class Caffeine(SingletonService):
    """Service to keep the screen awake by holding a logind idle inhibitor lock."""

    def __init__(self, **kwargs):
        self._fd: int | None = None
        self._external = False
        super().__init__(**kwargs)
        self._restore_state()

    def _restore_state(self):
        """Reflect an idle inhibitor that another process already holds."""
        if _idle_inhibitor_active():
            self._external = True
            self.notify("active")

    @Property(bool, "read-write", default_value=False)
    def active(self) -> bool:
        return self._fd is not None or self._external

    @active.setter
    def active(self, value: bool):
        if value == self.active:
            return
        if value:
            self._external = False
            self._fd = _take_idle_lock()
        else:
            self._external = False
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
        self.notify("active")


def _get_logind_proxy() -> Gio.DBusProxy | None:
    """Return the shared logind Manager proxy, creating it on first use."""
    global _LOGIND_PROXY
    if _LOGIND_PROXY is None:
        try:
            _LOGIND_PROXY = Gio.DBusProxy.new_sync(
                Gio.bus_get_sync(Gio.BusType.SYSTEM, None),
                Gio.DBusProxyFlags.NONE,
                None,
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
                "org.freedesktop.login1.Manager",
                None,
            )
        except GLib.Error as e:
            logger.error(f"[Caffeine] Couldn't connect to logind: {e.message}")
            return None
    return _LOGIND_PROXY


def _idle_inhibitor_active() -> bool:
    """True if logind reports a blocking idle inhibitor from anyone."""
    proxy = _get_logind_proxy()
    if proxy is None:
        return False
    try:
        reply = proxy.call_sync(
            "ListInhibitors",
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
    except GLib.Error as e:
        logger.error(f"[Caffeine] Couldn't read the inhibitor list: {e.message}")
        return False
    for what, _who, _why, mode, _uid, _pid in reply.unpack()[0]:
        if mode == "block" and "idle" in what.split(":"):
            return True
    return False


def _take_idle_lock() -> int | None:
    proxy = _get_logind_proxy()
    if proxy is None:
        return None
    try:
        reply, fd_list = proxy.call_with_unix_fd_list_sync(
            "Inhibit",
            GLib.Variant("(ssss)", ("idle", "Fabric", "Caffeine is on", "block")),
            GLib.VariantType("(h)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )
    except GLib.Error as e:
        logger.error(f"[Caffeine] Couldn't take the idle lock: {e.message}")
        return None
    # steal the fds so the list doesn't close the lock when it's freed
    fds = fd_list.steal_fds()
    index = reply.unpack()[0]
    for i, fd in enumerate(fds):
        if i != index:
            os.close(fd)
    return fds[index]

"""UDisks2-backed filesystem discovery, usage and mounting.

Adapted from fabric-bar's ``StorageManager``, using Gio D-Bus so Tsumiki does
not take a python-dbus dependency.
"""

import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fabric.core.service import Signal
from fabric.utils import Gio, GLib, logger

from services.base import SingletonService

UDISKS2_SERVICE = "org.freedesktop.UDisks2"
UDISKS2_PATH = "/org/freedesktop/UDisks2"
UDISKS2_FS_IFACE = "org.freedesktop.UDisks2.Filesystem"
UDISKS2_BLOCK_IFACE = "org.freedesktop.UDisks2.Block"
UDISKS2_PARTITION_IFACE = "org.freedesktop.UDisks2.Partition"
DBUS_OBJ_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"

BYTES_PER_GB = 1073741824
MIN_MOUNTABLE_BYTES = 2 * 1024**3  # Ignore < 2 GB (EFI / Windows recovery)
IGNORED_FS_TYPES = {"swap", "vfat", "iso9660", "squashfs"}
IGNORED_LABELS = {"system reserved", "recovery", "winre tools", "efi", "esp"}

# Long enough for a cold udisks2, short enough not to wedge the GTK loop.
CALL_TIMEOUT_MS = 5000


def format_mount_error(err: Exception) -> str:
    """Turn a D-Bus / UDisks2 error into a concise, readable reason string."""
    raw = str(err).strip()
    if ": " in raw:
        raw = raw.split(": ", 1)[1].strip()
    return raw.splitlines()[0].strip() if raw else "Unknown error"


@dataclass
class DiskMountInfo:
    """One UDisks2 filesystem and its current mount points."""

    object_path: str
    device_node: str
    mount_points: list[str] = field(default_factory=list)
    filesystem_type: str = ""
    label: str = ""
    size_bytes: int = 0

    @property
    def display_name(self) -> str:
        return self.label or self.device_node or self.object_path


class DisksService(SingletonService):
    """Discover UDisks2 filesystems and mount or unmount them asynchronously."""

    @Signal
    def disk_inserted(self) -> None:
        """Emitted when a filesystem appears; see ``last_inserted_disk``."""

    @Signal
    def disk_mounted(self) -> None:
        """Emitted after a successful mount; see ``last_mounted_disk``."""

    def __init__(self, **kwargs):
        if not self._init_once():
            return
        super().__init__(**kwargs)

        self._known_disks: dict[str, DiskMountInfo] = {}
        self._recent_notified: dict[str, float] = {}
        self.last_inserted_disk: DiskMountInfo | None = None
        self.last_mounted_disk: tuple[DiskMountInfo, str] | None = None
        self._min_size_bytes = MIN_MOUNTABLE_BYTES
        self._ignored_fs_types = {s.lower() for s in IGNORED_FS_TYPES}
        self._ignored_labels = {s.lower() for s in IGNORED_LABELS}
        self._ignored_devices: set[str] = set()

        self._bus: Gio.DBusConnection | None = None
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as e:
            logger.warning(f"[Disks] System bus unavailable: {e.message}")
            return

        self._bus.signal_subscribe(
            UDISKS2_SERVICE,
            DBUS_OBJ_MANAGER_IFACE,
            "InterfacesAdded",
            UDISKS2_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_interfaces_added,
        )

    # ── Discovery ────────────────────────────────────────────────

    @staticmethod
    def _decode_byte_array(raw: Any) -> str:
        if not raw:
            return ""
        data = bytes(int(b) for b in raw).rstrip(b"\x00")
        return data.decode("utf-8", errors="replace")

    def _build_disk_info_from_ifaces(
        self, object_path: str, ifaces: dict[str, Any]
    ) -> DiskMountInfo | None:
        if UDISKS2_FS_IFACE not in ifaces:
            return None
        return self._build_block_info(object_path, ifaces)

    def _build_block_info(
        self, object_path: str, ifaces: dict[str, Any]
    ) -> DiskMountInfo | None:
        """Flatten a Block (and optional Filesystem) entry into one record."""
        block_props = ifaces.get(UDISKS2_BLOCK_IFACE)
        if not block_props:
            return None

        fs_props = ifaces.get(UDISKS2_FS_IFACE, {})
        mounts = [
            m
            for m in (
                self._decode_byte_array(mp) for mp in fs_props.get("MountPoints", [])
            )
            if m
        ]

        return DiskMountInfo(
            object_path=str(object_path),
            device_node=self._decode_byte_array(
                block_props.get("PreferredDevice") or block_props.get("Device")
            ),
            mount_points=mounts,
            filesystem_type=str(block_props.get("IdType", "")),
            label=str(block_props.get("IdLabel", "")),
            size_bytes=int(block_props.get("Size", 0)),
        )

    def _managed_objects(self) -> dict[str, dict[str, Any]] | None:
        if self._bus is None:
            return None
        try:
            reply = self._bus.call_sync(
                UDISKS2_SERVICE,
                UDISKS2_PATH,
                DBUS_OBJ_MANAGER_IFACE,
                "GetManagedObjects",
                None,
                GLib.VariantType.new("(a{oa{sa{sv}}})"),
                Gio.DBusCallFlags.NONE,
                CALL_TIMEOUT_MS,
                None,
            )
            return reply.unpack()[0]
        except GLib.Error as e:
            logger.warning(f"[Disks] Failed to query UDisks2 objects: {e.message}")
            return None

    def list_filesystems(self) -> list[DiskMountInfo]:
        managed = self._managed_objects()
        if managed is None:
            return []

        results: list[DiskMountInfo] = []
        for path, ifaces in managed.items():
            info = self._build_disk_info_from_ifaces(str(path), ifaces)
            if info:
                self._known_disks[info.object_path] = info
                results.append(info)
        return results

    def get_disk_info(self, object_path: str) -> DiskMountInfo | None:
        managed = self._managed_objects()
        if managed is None:
            return None
        ifaces = managed.get(object_path)
        if not ifaces:
            return None
        info = self._build_disk_info_from_ifaces(str(object_path), ifaces)
        if info:
            self._known_disks[info.object_path] = info
        return info

    def should_ignore(self, disk: DiskMountInfo) -> bool:
        if (
            disk.device_node in self._ignored_devices
            or disk.object_path in self._ignored_devices
        ):
            return True
        if disk.filesystem_type.lower() in self._ignored_fs_types:
            return True
        if disk.label.strip().lower() in self._ignored_labels:
            return True
        return bool(
            self._min_size_bytes > 0 and 0 < disk.size_bytes < self._min_size_bytes
        )

    def list_unmounted_filesystems(self) -> list[DiskMountInfo]:
        """Return mountable, unmounted filesystems after filtering system partitions."""
        return [
            fs
            for fs in self.list_filesystems()
            if not fs.mount_points and not self.should_ignore(fs)
        ]

    def get_usage(self, path: str):
        return shutil.disk_usage(path)

    def list_partitions(self, all_partitions: bool = False) -> list[DiskMountInfo]:
        """List UDisks2 partitions, including unmounted and unformatted ones.

        ``all_partitions`` keeps entries the default filter drops, such as
        system/recovery partitions and small ESPs.
        """
        managed = self._managed_objects()
        if managed is None:
            return []

        results: list[DiskMountInfo] = []
        for path, ifaces in managed.items():
            if UDISKS2_PARTITION_IFACE not in ifaces:
                continue
            info = self._build_block_info(str(path), ifaces)
            if info is None:
                continue
            self._known_disks[info.object_path] = info
            if all_partitions or not self.should_ignore(info):
                results.append(info)
        return results

    # ── Mounting ─────────────────────────────────────────────────

    def mount(
        self,
        object_path: str,
        options: dict[str, Any] | None = None,
        on_success: Callable[[str], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        if self._bus is None:
            self._report_mount_error(
                object_path,
                RuntimeError("System bus unavailable"),
                on_error,
            )
            return

        disk_info = self._known_disks.get(object_path)
        params = GLib.Variant("(a{sv})", (options or {},))

        def _reply(bus, result, *_):
            try:
                mount_path = str(bus.call_finish(result).unpack()[0])
            except Exception as e:
                self._report_mount_error(object_path, e, on_error)
                return
            info = disk_info or DiskMountInfo(
                object_path=object_path, device_node=object_path
            )
            info.mount_points = [mount_path]
            self._known_disks[object_path] = info
            self.last_mounted_disk = (info, mount_path)
            self.emit("disk_mounted")
            if on_success:
                on_success(mount_path)

        self._bus.call(
            UDISKS2_SERVICE,
            object_path,
            UDISKS2_FS_IFACE,
            "Mount",
            params,
            None,
            Gio.DBusCallFlags.NONE,
            CALL_TIMEOUT_MS,
            None,
            _reply,
        )

    def unmount(
        self,
        object_path: str,
        options: dict[str, Any] | None = None,
        on_success: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        if self._bus is None:
            self._report_mount_error(
                object_path,
                RuntimeError("System bus unavailable"),
                on_error,
            )
            return

        disk_info = self._known_disks.get(object_path)
        params = GLib.Variant("(a{sv})", (options or {},))

        def _reply(bus, result, *_):
            try:
                bus.call_finish(result)
            except Exception as e:
                self._report_mount_error(object_path, e, on_error)
                return
            if disk_info is not None:
                disk_info.mount_points = []
            if on_success:
                on_success()

        self._bus.call(
            UDISKS2_SERVICE,
            object_path,
            UDISKS2_FS_IFACE,
            "Unmount",
            params,
            None,
            Gio.DBusCallFlags.NONE,
            CALL_TIMEOUT_MS,
            None,
            _reply,
        )

    def _report_mount_error(
        self,
        object_path: str,
        err: Exception,
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        disk = self._known_disks.get(object_path)
        name = disk.display_name if disk else object_path
        reason = format_mount_error(err)
        logger.error(f"[Disks] Failed to mount or unmount {name}: {reason}")
        if on_error:
            on_error(err)

    # ── Hotplug ──────────────────────────────────────────────────

    def _accept_inserted_disk(self, info: DiskMountInfo) -> None:
        self._known_disks[info.object_path] = info
        if self.should_ignore(info):
            return
        self.last_inserted_disk = info
        self.emit("disk_inserted")

    def _on_interfaces_added(
        self,
        _connection,
        _sender,
        _object_path,
        _interface,
        _signal,
        parameters,
    ) -> None:
        try:
            path, interfaces = parameters.unpack()
        except (AttributeError, TypeError, ValueError) as e:
            logger.warning(f"[Disks] Bad InterfacesAdded payload: {e}")
            return
        if UDISKS2_FS_IFACE not in interfaces:
            return

        object_path = str(path)
        now = time.monotonic()
        if now - self._recent_notified.get(object_path, 0.0) < 3.0:
            return
        self._recent_notified[object_path] = now

        info = self._build_disk_info_from_ifaces(object_path, interfaces)
        if info is not None:
            self._accept_inserted_disk(info)
            return
        self._resolve_inserted_disk_async(object_path)

    def _resolve_inserted_disk_async(self, object_path: str) -> None:
        """InterfacesAdded may arrive before the Block interface; re-read it."""

        def _reply(bus, result, *_):
            try:
                managed = bus.call_finish(result).unpack()[0]
            except GLib.Error as e:
                logger.warning(
                    f"[Disks] Async GetManagedObjects failed for {object_path}: "
                    f"{e.message}"
                )
                return
            ifaces = managed.get(object_path)
            if not ifaces:
                return
            info = self._build_disk_info_from_ifaces(object_path, ifaces)
            if info:
                self._accept_inserted_disk(info)

        if self._bus is not None:
            self._bus.call(
                UDISKS2_SERVICE,
                UDISKS2_PATH,
                DBUS_OBJ_MANAGER_IFACE,
                "GetManagedObjects",
                None,
                GLib.VariantType.new("(a{oa{sa{sv}}})"),
                Gio.DBusCallFlags.NONE,
                CALL_TIMEOUT_MS,
                None,
                _reply,
            )

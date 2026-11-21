"""Tests for the Gio port of fabric-bar's UDisks2 storage manager."""

import unittest
from unittest import mock

from services.disks import (
    UDISKS2_BLOCK_IFACE,
    UDISKS2_FS_IFACE,
    UDISKS2_PARTITION_IFACE,
    DiskMountInfo,
    DisksService,
    format_mount_error,
)

FILESYSTEM = {
    UDISKS2_FS_IFACE: {"MountPoints": [b"/mnt/usb\x00"]},
    UDISKS2_BLOCK_IFACE: {
        "PreferredDevice": b"/dev/sdb1\x00",
        "IdType": "ext4",
        "IdLabel": "USB",
        "Size": 8 * 1024**3,
    },
}


def _service() -> DisksService:
    service = DisksService.__new__(DisksService)
    service._known_disks = {}
    service._recent_notified = {}
    service._min_size_bytes = 2 * 1024**3
    service._ignored_fs_types = {"swap", "vfat"}
    service._ignored_labels = {"efi"}
    service._ignored_devices = set()
    service.last_inserted_disk = None
    service.last_mounted_disk = None
    service._bus = mock.Mock()
    service.emit = mock.Mock()
    return service


class FormatMountErrorTest(unittest.TestCase):
    """The D-Bus error prefix is noise in a user-facing reason."""

    def test_the_dbus_prefix_is_dropped(self):
        err = Exception("org.freedesktop.UDisks2.Error.Failed: not authorized\nmore")

        self.assertEqual("not authorized", format_mount_error(err))

    def test_an_empty_error_still_has_a_reason(self):
        self.assertEqual("Unknown error", format_mount_error(Exception("")))


class BuildDiskInfoTest(unittest.TestCase):
    """UDisks2 interfaces are flattened into one mount record."""

    def test_mount_points_and_block_properties_are_decoded(self):
        info = _service()._build_disk_info_from_ifaces("/p", FILESYSTEM)

        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual("/dev/sdb1", info.device_node)
        self.assertEqual(["/mnt/usb"], info.mount_points)
        self.assertEqual("ext4", info.filesystem_type)
        self.assertEqual("USB", info.label)
        self.assertEqual(8 * 1024**3, info.size_bytes)

    def test_a_block_without_a_filesystem_interface_is_skipped(self):
        self.assertIsNone(
            _service()._build_disk_info_from_ifaces(
                "/p", {UDISKS2_BLOCK_IFACE: {"Size": 8 * 1024**3}}
            )
        )


class ShouldIgnoreTest(unittest.TestCase):
    """System and tiny partitions never reach the mount list."""

    def test_small_partitions_are_ignored(self):
        service = _service()

        self.assertTrue(
            service.should_ignore(
                DiskMountInfo("/p", "/dev/sdb1", size_bytes=512 * 1024**2)
            )
        )

    def test_system_filesystems_and_labels_are_ignored(self):
        service = _service()

        self.assertTrue(
            service.should_ignore(DiskMountInfo("/p", "/dev/sdb1", ["/"], "vfat"))
        )
        self.assertTrue(
            service.should_ignore(DiskMountInfo("/p", "/dev/sdb1", label="EFI"))
        )

    def test_a_normal_partition_is_kept(self):
        self.assertFalse(
            _service().should_ignore(
                DiskMountInfo(
                    "/p", "/dev/sdb1", filesystem_type="ext4", size_bytes=8 * 1024**3
                )
            )
        )


class DiscoveryTest(unittest.TestCase):
    """Listings come from the UDisks2 object manager."""

    def test_only_unmounted_filesystems_are_listed(self):
        service = _service()
        service._managed_objects = mock.Mock(
            return_value={
                "/mounted": {
                    UDISKS2_FS_IFACE: {"MountPoints": [b"/mnt/a\x00"]},
                    UDISKS2_BLOCK_IFACE: {"Size": 8 * 1024**3, "IdType": "ext4"},
                },
                "/unmounted": {
                    UDISKS2_FS_IFACE: {"MountPoints": []},
                    UDISKS2_BLOCK_IFACE: {"Size": 8 * 1024**3, "IdType": "ext4"},
                },
            }
        )

        filesystems = service.list_unmounted_filesystems()

        self.assertEqual(["/unmounted"], [fs.object_path for fs in filesystems])

    def test_a_failed_query_lists_nothing(self):
        service = _service()
        service._managed_objects = mock.Mock(return_value=None)

        self.assertEqual([], service.list_filesystems())

    def test_partitions_come_from_udisks2_not_psutil(self):
        service = _service()
        service._managed_objects = mock.Mock(
            return_value={
                "/partition": {
                    UDISKS2_PARTITION_IFACE: {},
                    UDISKS2_BLOCK_IFACE: {
                        "Device": b"/dev/sdb1\x00",
                        "IdType": "ext4",
                        "Size": 8 * 1024**3,
                    },
                },
                "/whole-disk": {
                    UDISKS2_BLOCK_IFACE: {
                        "Device": b"/dev/sdb\x00",
                        "Size": 16 * 1024**3,
                    }
                },
            }
        )

        partitions = service.list_partitions()

        self.assertEqual(["/partition"], [p.object_path for p in partitions])
        self.assertEqual("/dev/sdb1", partitions[0].device_node)

    def test_partition_filtering_can_be_disabled(self):
        service = _service()
        service._managed_objects = mock.Mock(
            return_value={
                "/esp": {
                    UDISKS2_PARTITION_IFACE: {},
                    UDISKS2_BLOCK_IFACE: {
                        "Device": b"/dev/sdb1\x00",
                        "IdType": "vfat",
                        "Size": 512 * 1024**2,
                    },
                }
            }
        )

        self.assertEqual([], service.list_partitions())
        self.assertEqual(
            ["/esp"],
            [p.object_path for p in service.list_partitions(all_partitions=True)],
        )


class MountTest(unittest.TestCase):
    """Mount and unmount post their result back on the main loop."""

    def _run_reply(self, service, path="/mnt/usb"):
        callback = service._bus.call.call_args.args[9]
        service._bus.call_finish.return_value.unpack.return_value = (path,)
        callback(service._bus, mock.Mock())

    def test_mount_reports_the_resolved_path(self):
        service = _service()
        service._known_disks["/p"] = DiskMountInfo("/p", "/dev/sdb1")
        on_success = mock.Mock()

        service.mount("/p", on_success=on_success)
        self._run_reply(service)

        on_success.assert_called_once_with("/mnt/usb")
        self.assertEqual(
            ("/p", ["/mnt/usb"]),
            (
                service.last_mounted_disk[0].object_path,
                service.last_mounted_disk[0].mount_points,
            ),
        )
        service.emit.assert_called_once_with("disk_mounted")

    def test_mount_failure_reaches_the_error_callback(self):
        service = _service()
        on_error = mock.Mock()
        service._bus.call_finish.side_effect = Exception("denied")

        service.mount("/p", on_error=on_error)
        callback = service._bus.call.call_args.args[9]
        callback(service._bus, mock.Mock())

        on_error.assert_called_once()
        service.emit.assert_not_called()

    def test_unmount_clears_the_cached_mount_points(self):
        service = _service()
        info = DiskMountInfo("/p", "/dev/sdb1", ["/mnt/usb"])
        service._known_disks["/p"] = info

        service.unmount("/p")
        callback = service._bus.call.call_args.args[9]
        callback(service._bus, mock.Mock())

        self.assertEqual([], info.mount_points)


class InterfacesAddedTest(unittest.TestCase):
    """Hotplug signals are filtered and cached before being announced."""

    def _parameters(self, path, interfaces):
        parameters = mock.Mock()
        parameters.unpack.return_value = (path, interfaces)
        return parameters

    def test_a_new_filesystem_is_announced(self):
        service = _service()

        service._on_interfaces_added(
            None, None, None, None, None, self._parameters("/p", FILESYSTEM)
        )

        self.assertEqual("/p", service.last_inserted_disk.object_path)
        service.emit.assert_called_once_with("disk_inserted")

    def test_ignored_and_system_filesystems_stay_quiet(self):
        service = _service()
        interfaces = {
            UDISKS2_FS_IFACE: {"MountPoints": []},
            UDISKS2_BLOCK_IFACE: {"IdType": "vfat", "Size": 8 * 1024**3},
        }

        service._on_interfaces_added(
            None, None, None, None, None, self._parameters("/p", interfaces)
        )

        service.emit.assert_not_called()

    def test_a_bad_payload_is_ignored(self):
        service = _service()
        parameters = mock.Mock()
        parameters.unpack.side_effect = ValueError("bad")

        service._on_interfaces_added(None, None, None, None, None, parameters)

        service.emit.assert_not_called()


if __name__ == "__main__":
    unittest.main()

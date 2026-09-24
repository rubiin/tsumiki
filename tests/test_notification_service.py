import json
import os
import tempfile
import unittest
from unittest import mock

from fabric.notifications import Notification
from gi.repository import GLib

from services.custom_notification import CustomNotifications


def make_notification(
    *,
    notification_id: int = 1,
    replaces_id: int = 0,
    app_name: str = "test-app",
    summary: str = "summary",
    body: str = "body",
    sync_hint: str | None = None,
    sync_value: str = "progress-key",
) -> Notification:
    """Build a Notification without DBus/GTK, optionally with a sync hint."""
    data = {
        "id": notification_id,
        "replaces-id": replaces_id,
        "app-name": app_name,
        "app-icon": "",
        "summary": summary,
        "body": body,
        "timeout": 5000,
        "urgency": 1,
        "actions": [],
        "image-file": None,
        "image-pixmap": None,
        "time": 100.0,
    }
    notification = Notification.deserialize(data)
    hints = {}
    if sync_hint is not None:
        hints[sync_hint] = GLib.Variant("s", sync_value)
    notification._hints = GLib.Variant("a{sv}", hints)
    return notification


def run_inline(func, *args, **kwargs):
    """Run a thread-pool submission synchronously so tests stay deterministic."""
    return func(*args, **kwargs)


class CustomNotificationsTest(unittest.TestCase):
    """Test replace_id / sync-hint replacement in the notification service."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._cache_file = os.path.join(self._tmpdir.name, "notifications.json")

        patchers = [
            mock.patch(
                "services.custom_notification.NOTIFICATION_CACHE_FILE",
                self._cache_file,
            ),
            # Avoid owning the real DBus name in tests.
            mock.patch("gi.repository.Gio.bus_own_name", return_value=1),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self._tmpdir.cleanup)

        self.service = CustomNotifications()

    def test_replaces_id_updates_in_place(self):
        self.service.cache_notification({}, make_notification(summary="old"), 100)

        replacement = make_notification(replaces_id=1, summary="new", body="updated")
        self.service.cache_notification({}, replacement, 100)

        self.assertEqual(len(self.service.all_notifications), 1)
        entry = self.service.all_notifications[0]
        self.assertEqual(entry["id"], 1)
        self.assertEqual(entry["summary"], "new")
        self.assertEqual(entry["body"], "updated")

    def test_replaces_id_missing_target_appends(self):
        self.service.cache_notification({}, make_notification(summary="first"), 100)

        self.service.cache_notification(
            {}, make_notification(replaces_id=999, summary="orphan"), 100
        )

        self.assertEqual(len(self.service.all_notifications), 2)
        self.assertEqual(self.service.all_notifications[1]["id"], 2)
        self.assertEqual(self.service._count, 2)

    def test_sync_hint_replaces_in_place(self):
        self.service.cache_notification(
            {}, make_notification(sync_hint="synchronous", summary="old"), 100
        )
        self.service.cache_notification(
            {}, make_notification(sync_hint="synchronous", summary="new"), 100
        )

        self.assertEqual(len(self.service.all_notifications), 1)
        self.assertEqual(self.service.all_notifications[0]["id"], 1)
        self.assertEqual(self.service.all_notifications[0]["summary"], "new")
        self.assertEqual(self.service._synchronous_ids["progress-key"], 1)

    def test_private_sync_hint_keys_also_replace(self):
        # Writes are drained inline so the service rebuilt on each iteration sees
        # the previously persisted entry.
        with mock.patch("services.custom_notification.thread", side_effect=run_inline):
            for hint in ("private-synchronous", "x-canonical-private-synchronous"):
                with self.subTest(hint=hint):
                    service = CustomNotifications()
                    service.cache_notification(
                        {}, make_notification(sync_hint=hint, summary="old"), 100
                    )
                    service.cache_notification(
                        {}, make_notification(sync_hint=hint, summary="new"), 100
                    )
                    self.assertEqual(len(service.all_notifications), 1)
                    self.assertEqual(service.all_notifications[0]["summary"], "new")

    def test_replacement_does_not_advance_count(self):
        self.service.cache_notification({}, make_notification(summary="old"), 100)
        self.assertEqual(self.service._count, 1)

        self.service.cache_notification(
            {}, make_notification(replaces_id=1, summary="new"), 100
        )
        self.assertEqual(self.service._count, 1)
        self.assertEqual(len(self.service.all_notifications), 1)

        self.service.cache_notification({}, make_notification(summary="fresh"), 100)
        self.assertEqual(self.service._count, 2)
        self.assertEqual(len(self.service.all_notifications), 2)
        self.assertEqual(self.service.all_notifications[1]["id"], 2)

    def test_replacement_respects_per_app_limit(self):
        widget_config = {"notification": {"per_app_limits": {"test-app": 1}}}

        self.service.cache_notification(
            widget_config, make_notification(summary="old"), 100
        )
        self.service.cache_notification(
            widget_config, make_notification(replaces_id=1, summary="new"), 100
        )

        # The in-place update is already counted - no extra eviction.
        self.assertEqual(len(self.service.all_notifications), 1)
        self.assertEqual(self.service.all_notifications[0]["summary"], "new")

    def test_notification_count_emitted_on_replacement(self):
        counts = []
        self.service.connect(
            "notification_count", lambda *args: counts.append(args[-1])
        )

        self.service.cache_notification({}, make_notification(summary="old"), 100)
        self.service.cache_notification(
            {}, make_notification(replaces_id=1, summary="new"), 100
        )

        self.assertEqual(counts[-1], 1)
        self.assertEqual(self.service.count, 1)

    def test_sync_map_restored_from_cache(self):
        # Persistence is off-thread, so drain queued writes before rebuilding
        # the service from the cache file.
        with mock.patch("services.custom_notification.thread", side_effect=run_inline):
            self.service.cache_notification(
                {}, make_notification(sync_hint="synchronous", summary="old"), 100
            )
            restored = CustomNotifications()
        self.assertEqual(restored._synchronous_ids, {"progress-key": 1})

        restored.cache_notification(
            {}, make_notification(sync_hint="synchronous", summary="new"), 100
        )
        self.assertEqual(len(restored.all_notifications), 1)
        self.assertEqual(restored.all_notifications[0]["id"], 1)
        self.assertEqual(restored.all_notifications[0]["summary"], "new")

    def test_drop_registry_entry_leaves_history_untouched(self):
        self.service._notifications = {1: make_notification()}
        self.service.all_notifications = [
            {
                "id": 1,
                "replaces-id": 0,
                "app-name": "test-app",
                "app-icon": "",
                "summary": "s",
                "body": "b",
                "timeout": 5000,
                "urgency": 1,
                "actions": [],
                "image-file": None,
                "image-pixmap": None,
                "time": 100.0,
            }
        ]

        self.service.drop_registry_entry(1)

        self.assertNotIn(1, self.service._notifications)
        self.assertEqual(len(self.service.all_notifications), 1)

    def test_cache_notification_does_not_deserialize_history(self):
        """Adding a notification must not re-deserialize the whole history."""
        self.service.cache_notification({}, make_notification(summary="first"), 100)

        with mock.patch.object(
            self.service,
            "_deserialize_notification",
            wraps=self.service._deserialize_notification,
        ) as deserialize:
            self.service.cache_notification(
                {}, make_notification(summary="second"), 100
            )

        deserialize.assert_not_called()

    def test_persistence_is_off_thread_and_coalesced(self):
        submitted = []

        def fake_thread(target, *args, **kwargs):
            submitted.append(target)
            return mock.Mock()

        with mock.patch("services.custom_notification.thread", side_effect=fake_thread):
            for summary in ("a", "b", "c"):
                self.service.cache_notification(
                    {}, make_notification(summary=summary), 100
                )

        # One writer is queued and nothing was written on the calling thread.
        self.assertEqual(len(submitted), 1)
        self.assertFalse(os.path.exists(self._cache_file))

        # Draining the writer persists the newest snapshot in order.
        submitted[0]()
        with open(self._cache_file, encoding="utf-8") as handle:
            persisted = json.load(handle)
        self.assertEqual([n["summary"] for n in persisted], ["a", "b", "c"])

    def test_persist_failure_does_not_wedge_writer(self):
        """A failed write must not disable persistence for good."""
        submitted = []

        def capture(target, *args, **kwargs):
            submitted.append(target)
            return mock.Mock()

        with (
            mock.patch(
                "services.custom_notification.json.dump",
                side_effect=ValueError("bad"),
            ),
            mock.patch("services.custom_notification.thread", side_effect=capture),
        ):
            self.service.cache_notification({}, make_notification(summary="a"), 100)
            # Invoke the worker directly, the way the pool would: an escaping
            # error would leave the running flag set and drop later writes.
            submitted[0]()

        self.assertFalse(self.service._persist_running)

        with mock.patch("services.custom_notification.thread", side_effect=run_inline):
            self.service.cache_notification({}, make_notification(summary="b"), 100)

        with open(self._cache_file, encoding="utf-8") as handle:
            persisted = json.load(handle)
        self.assertEqual([n["summary"] for n in persisted], ["a", "b"])


if __name__ == "__main__":
    unittest.main()

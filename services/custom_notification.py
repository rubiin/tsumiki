import threading

from fabric import Signal
from fabric.notifications import Notification, Notifications, NotificationSerializedData
from fabric.utils import GdkPixbuf, logger, math, os

from utils.colors import Colors
from utils.constants import (
    NOTIFICATION_CACHE_FILE,
    NOTIFICATION_IMAGE_SIZE,
)
from utils.decorators import thread
from utils.functions import read_json_file, write_json_file
from utils.widget_utils import get_notification_image_pixbuf

_MAX_CACHED_PIXBUF = 100  # Hard cap on pixbuf cache entries

# Hint keys apps use to mark notifications that replace each other.
_SYNC_HINT_KEYS = (
    "synchronous",
    "private-synchronous",
    "x-canonical-private-synchronous",
)


class CustomNotifications(Notifications):
    """A service to manage the notifications."""

    @Signal
    def clear_all(self, value: bool) -> None:
        """Signal emitted when notifications are emptied."""
        # Implement as needed for your application

    @Signal
    def notification_count(self, value: int) -> None:
        """Signal emitted when a new notification is added."""
        # Implement as needed for your application

    @Signal
    def dnd(self, value: bool) -> None:
        """Signal emitted when dnd is toggled."""
        # Implement as needed for your application

    @property
    def count(self) -> int:
        """Return the count of notifications."""
        return len(self.all_notifications)

    @property
    def dont_disturb(self) -> bool:
        """Return the pause status."""
        return self._dont_disturb

    @dont_disturb.setter
    def dont_disturb(self, value: bool):
        """Set the pause status."""
        self._dont_disturb = value
        self.emit("dnd", value)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = threading.RLock()
        self.all_notifications = []
        self._count = 0  # Will be updated to highest ID when loading
        self.deserialized_notifications = []
        self._dont_disturb = False
        # Cache for pre-scaled pixbufs: {notification_id: {size: GdkPixbuf.Pixbuf}}
        self._pixbuf_cache: dict[int, dict[int, GdkPixbuf.Pixbuf]] = {}
        # Sync-hint map: {sync key: last notification id} (SwayNC parity).
        self._synchronous_ids: dict[str, int] = {}
        # Large and rewritten every change; never write on the caller's thread.
        self._persist_lock = threading.Lock()
        self._persist_pending = False
        self._persist_running = False
        self._load_notifications()

    def _load_notifications(self):
        """Read and validate notifications from the cache file."""
        if not os.path.exists(NOTIFICATION_CACHE_FILE):
            return

        try:
            original_data = read_json_file(NOTIFICATION_CACHE_FILE)

            if original_data is None:
                logger.info(f"{Colors.INFO}[Notification] Cache file is empty.")
                return

            if not isinstance(original_data, list):
                logger.warning(
                    f"{Colors.WARNING}[Notification] Invalid cache format, resetting"
                )
                write_json_file(NOTIFICATION_CACHE_FILE, [])
                return

            loaded_data = list(reversed(original_data))

            valid_notifications = []
            highest_id = self._count

            for notification in loaded_data:
                try:
                    self._deserialize_notification(notification)
                    valid_notifications.append(notification)
                    highest_id = max(highest_id, notification.get("id", 0))
                except Exception as e:
                    msg = f"[Notification] Invalid: {str(e)[:50]}"
                    logger.exception(f"{Colors.INFO}{msg}")

            # Only rewrite when validation changed something.
            if valid_notifications != loaded_data:
                write_json_file(NOTIFICATION_CACHE_FILE, valid_notifications)
                logger.info(
                    f"{Colors.INFO}[Notification] Notifications written successfully."
                )

            self.all_notifications = valid_notifications
            self._count = highest_id
            # Restored from persisted entries so the mapping survives restarts.
            self._synchronous_ids = {
                n["sync-key"]: n["id"] for n in valid_notifications if n.get("sync-key")
            }

            del valid_notifications
            del original_data
            del loaded_data

        except (KeyError, ValueError, IndexError) as e:
            logger.exception(f"{Colors.INFO}[Notification] {e}")

    def remove_notification(self, id: int):
        """Remove a notification by ID, ensuring thread safety."""
        with self._lock:
            item = next((p for p in self.all_notifications if p["id"] == id), None)
            if item:
                self.all_notifications.remove(item)
                self._pixbuf_cache.pop(id, None)
                self._persist_and_emit()

                if len(self.all_notifications) == 0:
                    self.emit("clear_all", True)

    def drop_registry_entry(self, notification_id: int):
        """Remove a notification from the in-memory registry only.

        ``remove_notification`` is overridden to act on persisted history, so
        replaced notifications need this narrower path.
        """
        return super().remove_notification(notification_id)

    def get_cached_pixbuf(
        self, notification_id: int, size: int | None = None
    ) -> GdkPixbuf.Pixbuf | None:
        """Get a cached pixbuf for a notification, optionally at a specific size."""
        if notification_id not in self._pixbuf_cache:
            return None

        cache = self._pixbuf_cache[notification_id]
        size = size or NOTIFICATION_IMAGE_SIZE

        if size in cache:
            return cache[size]

        if cache:
            largest_size = max(cache.keys())
            source_pixbuf = cache[largest_size]
            scaled = source_pixbuf.scale_simple(
                size, size, GdkPixbuf.InterpType.BILINEAR
            )
            if scaled:
                cache[size] = scaled
            return scaled

        return None

    def _evict_oldest_pixbuf(self):
        """Evict the oldest pixbuf entry when cache exceeds the cap."""
        while len(self._pixbuf_cache) > _MAX_CACHED_PIXBUF:
            # IDs are monotonically increasing, so the smallest ID is oldest
            oldest_id = min(self._pixbuf_cache.keys())
            del self._pixbuf_cache[oldest_id]

    def cache_pixbuf(
        self,
        notification_id: int,
        pixbuf: GdkPixbuf.Pixbuf,
        size: int | None = None,
    ) -> None:
        """Cache a pixbuf for a notification."""
        size = size or NOTIFICATION_IMAGE_SIZE
        if notification_id not in self._pixbuf_cache:
            self._pixbuf_cache[notification_id] = {}
        self._pixbuf_cache[notification_id][size] = pixbuf
        self._evict_oldest_pixbuf()

    def cache_pixbuf_from_notification(
        self, notification_id: int, notification: Notification
    ) -> None:
        """Cache a notification's image pixbuf at common sizes."""
        if pixbuf := get_notification_image_pixbuf(notification):
            base_size = NOTIFICATION_IMAGE_SIZE
            self.cache_pixbuf(notification_id, pixbuf, base_size)

            # 75% of the base size is what the date menu uses.
            smaller_size = math.ceil(0.75 * base_size)
            scaled_small = pixbuf.scale_simple(
                smaller_size, smaller_size, GdkPixbuf.InterpType.BILINEAR
            )
            if scaled_small:
                self.cache_pixbuf(notification_id, scaled_small, smaller_size)

    def cache_notification(self, widget_config, data: Notification, max_count: int):
        """Cache a notification, ensuring thread safety.

        A ``replaces_id`` or sync hint targeting a live entry updates it in
        place, so progress updates do not stack up history duplicates.
        """
        with self._lock:
            target_id = self._replacement_target_id(data)
            if target_id is not None:
                self._replace_notification_in_place(target_id, data)
                return

            new_notification = self._create_serialized_notification(data)
            notification_id = new_notification["id"]

            sync_key = self._get_sync_key(data)
            if sync_key:
                self._synchronous_ids[sync_key] = notification_id
                new_notification["sync-key"] = sync_key

            # Cache the pixbuf before the notification object is potentially GC'd
            self.cache_pixbuf_from_notification(notification_id, data)

            self._enforce_per_app_limit(widget_config, new_notification, max_count)
            self.all_notifications.append(new_notification)
            self._enforce_global_limit(max_count)
            self._persist_and_emit()

    def _notification_exists(self, notification_id: int) -> bool:
        """Return whether a notification with the given id is in history."""
        return any(n["id"] == notification_id for n in self.all_notifications)

    def _get_sync_key(self, data: Notification) -> str | None:
        """Return the sync-hint key for a notification, or ``None``."""
        getter = getattr(data, "do_get_hint_entry", None)
        if getter is None:
            return None
        for hint in _SYNC_HINT_KEYS:
            try:
                value = getter(hint)
            except Exception:
                value = None
            if value:
                return str(value)
        return None

    def _replacement_target_id(self, data: Notification) -> int | None:
        """Compute the id of the entry this notification should replace.

        A live ``replaces_id`` wins; otherwise the sync-hint map is consulted.
        ``None`` means append.
        """
        replaces_id = getattr(data, "replaces_id", 0) or 0
        if replaces_id and self._notification_exists(replaces_id):
            return replaces_id

        sync_key = self._get_sync_key(data)
        if sync_key:
            previous_id = self._synchronous_ids.get(sync_key)
            if previous_id and self._notification_exists(previous_id):
                return previous_id
        return None

    def _replace_notification_in_place(self, target_id: int, data: Notification):
        """Update an existing history entry with a replacement notification.

        The id and list position are preserved, keeping the pixbuf cache
        consistent; limits are not re-enforced because the entry is already counted.
        """
        serialized = data.serialize()
        serialized.update({"id": target_id, "app_name": data.app_name})

        sync_key = self._get_sync_key(data)
        if sync_key:
            self._synchronous_ids[sync_key] = target_id
            serialized["sync-key"] = sync_key

        for i, entry in enumerate(self.all_notifications):
            if entry["id"] == target_id:
                self.all_notifications[i] = serialized
                break

        # Re-cache the pixbuf (id is unchanged, so the old entry is reused)
        self.cache_pixbuf_from_notification(target_id, data)
        self._persist_and_emit()

    def _create_serialized_notification(self, data: Notification) -> dict:
        """Generate a new notification with a unique ID."""
        self._count += 1
        serialized = data.serialize()
        serialized.update(
            {
                "id": self._count,
                "app_name": data.app_name,
            }
        )
        return serialized

    def _enforce_global_limit(self, max_count: int):
        """Remove oldest notifications if total count exceeds global limit."""
        while len(self.all_notifications) > max_count:
            oldest = self.all_notifications.pop(0)
            oldest_id = oldest["id"]
            self._pixbuf_cache.pop(oldest_id, None)
            self.emit("notification-closed", oldest_id, "dismissed-by-limit")

    def _enforce_per_app_limit(
        self, widget_config, new_notification: dict, max_count: int
    ):
        """Ensure per-app limits are respected."""
        app_name = new_notification["app_name"]
        per_app_limits = widget_config.get("notification", {}).get("per_app_limits", {})
        app_limit = per_app_limits.get(app_name, max_count)

        app_notifications = [
            n for n in self.all_notifications if n["app_name"] == app_name
        ]

        if len(app_notifications) >= app_limit:
            app_notifications.sort(key=lambda x: x["id"])
            to_remove = len(app_notifications) - app_limit + 1
            for old in app_notifications[:to_remove]:
                self.all_notifications.remove(old)
                old_id = old["id"]
                self._pixbuf_cache.pop(old_id, None)
                self.emit("notification-closed", old_id, "dismissed-by-limit")

    def _deserialize_notification(self, notification: NotificationSerializedData):
        """Deserialize a notification."""
        return Notification.deserialize(notification)

    def _persist_and_emit(self):
        """Queue a background write of the history, then emit signals.

        Bursts (e.g. progress updates) only mark the snapshot dirty instead of
        stacking up one full rewrite per notification.
        """
        self._schedule_persist()
        self.emit("notification_count", len(self.all_notifications))

    def _schedule_persist(self):
        """Start the writer thread unless one is already draining the queue."""
        with self._persist_lock:
            self._persist_pending = True
            if self._persist_running:
                return
            self._persist_running = True
        try:
            thread(self._persist_loop)
        except Exception as e:
            # Submission fails once the pool shuts down; the flag reset matters.
            with self._persist_lock:
                self._persist_running = False
            logger.exception(f"Failed to schedule notifications persist: {e}")

    def _persist_loop(self):
        """Write the latest snapshot, looping while newer writes are queued.

        A single worker keeps the file in sync with the newest state under bursts.
        """
        while True:
            with self._persist_lock:
                if not self._persist_pending:
                    self._persist_running = False
                    return
                self._persist_pending = False
                # Entries are replaced wholesale, so a shallow copy is stable.
                snapshot = list(self.all_notifications)
            try:
                # sync=True: this already runs on the dedicated writer thread.
                write_json_file(NOTIFICATION_CACHE_FILE, snapshot, sync=True)
            except Exception as e:
                # Escaping would skip the flag reset and wedge persistence.
                logger.exception(f"Failed to persist notifications: {e}")

    def clear_all_notifications(self):
        """Empty the notifications (thread-safe)."""
        logger.info("[Notification] Clearing all notifications")

        with self._lock:
            highest_id = self._count

            self.all_notifications = []
            self._pixbuf_cache.clear()

            self._persist_and_emit()

            logger.info(
                f"{Colors.INFO}[Notification] Notifications written successfully."
            )

            self.emit("clear_all", True)

            # Restore the ID counter so new notifications get unique IDs
            self._count = highest_id

    def deserialize_with_id(self, notification):
        """Helper to deserialize and return result with ID."""
        try:
            return (self._deserialize_notification(notification), None)
        except Exception as e:
            msg = f"[Notification] Deserialize failed: {str(e)[:50]}"
            logger.exception(f"{Colors.INFO}{msg}")
            return (None, notification.get("id"))

    def get_deserialized(self) -> list[Notification]:
        """Return the notifications."""
        results = [
            self.deserialize_with_id(notification)
            for notification in self.all_notifications
        ]

        deserialized = []
        invalid_ids = []
        for result, error_id in results:
            if result is not None:
                deserialized.append(result)
            elif error_id is not None:
                invalid_ids.append(error_id)

        for invalid_id in invalid_ids:
            self.remove_notification(invalid_id)

        return deserialized

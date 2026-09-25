"""Shared test fixtures.

Notification payloads and the ``TsumikiConfig`` mock setup were rebuilt
per test file; keeping one copy here stops the fixture from drifting away
from the shapes production code actually deserializes.
"""

from collections.abc import Callable
from typing import Any
from unittest import mock

from fabric.notifications import Notification
from gi.repository import GLib

DEFAULT_PARSED_CONFIG = {
    "general": {},
    "widgets": {},
    "layout": {},
    "modules": {},
    "styling": {},
}

# Distinguishes "argument not passed" (use the default config) from an
# explicit ``parsed_data=None`` (the defaults path in ``_load_config``).
_UNSET = object()


def notification_data(**overrides: Any) -> dict[str, Any]:
    """Return a serialized notification payload, as persisted in the cache."""
    data: dict[str, Any] = {
        "id": 1,
        "replaces-id": 0,
        "app-name": "test-app",
        "app-icon": "",
        "summary": "summary",
        "body": "body",
        "timeout": 5000,
        "urgency": 1,
        "actions": [],
        "image-file": None,
        "image-pixmap": None,
        "time": 100.0,
    }
    data.update(overrides)
    return data


def make_notification(
    notification_id: int = 1,
    *,
    replaces_id: int = 0,
    app_name: str = "test-app",
    summary: str = "summary",
    body: str = "body",
    timeout: int = 5000,
    urgency: int = 1,
    sync_hint: str | None = None,
    sync_value: str = "progress-key",
) -> Notification:
    """Build a Notification without DBus/GTK, optionally carrying a sync hint."""
    notification = Notification.deserialize(
        notification_data(
            **{
                "id": notification_id,
                "replaces-id": replaces_id,
                "app-name": app_name,
                "summary": summary,
                "body": body,
                "timeout": timeout,
                "urgency": urgency,
            }
        )
    )
    hints = {}
    if sync_hint is not None:
        hints[sync_hint] = GLib.Variant("s", sync_value)
    # A live notification always has hints, even when none were sent.
    notification._hints = GLib.Variant("a{sv}", hints)
    return notification


def make_tsumiki_config(
    parsed_data: Any = _UNSET,
    *,
    exists: bool = True,
    enums_error: BaseException | None = None,
):
    """Construct a ``TsumikiConfig`` with the file and validation layers mocked.

    *parsed_data* is what ``read_toml_file`` returns - omit it for the standard
    config, pass ``None`` to exercise the defaults path, or a dict to control
    it exactly. *exists* makes ``config.toml`` look absent; *enums_error* makes
    enum validation fail.

    Callers that care about singleton identity must reset
    ``TsumikiConfig._instance`` themselves, so the patches still run.
    """
    from utils.config import TsumikiConfig

    if parsed_data is _UNSET:
        parsed_data = dict(DEFAULT_PARSED_CONFIG)

    with (
        mock.patch("utils.config.get_relative_path", return_value="/tmp"),
        mock.patch("utils.config.os.path.exists", return_value=exists),
        mock.patch("utils.config.read_toml_file", return_value=parsed_data),
        mock.patch(
            "utils.config.validate_config_enums", side_effect=enums_error or None
        ),
        mock.patch("utils.config.validate_widgets"),
    ):
        return TsumikiConfig()


def run_inline(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a thread-pool submission synchronously so tests stay deterministic."""
    return func(*args, **kwargs)

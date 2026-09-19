"""Tests for utils/config_watcher.py — config file change watcher."""

import hashlib
import os
import tempfile
import unittest
from unittest import mock

from utils.config_watcher import (
    _CONFIG_FILES,
    _DEFAULT_RESTART_DELAY,
    _RESTART_COOLDOWN_MS,
    ConfigWatcher,
    start_config_watching,
    stop_config_watching,
)

_DONE_HINT = mock.sentinel.done_hint


class ConfigConstantsTest(unittest.TestCase):
    """Verify module-level constants are sensible."""

    def test_restart_delay_positive(self):
        self.assertGreater(_DEFAULT_RESTART_DELAY, 0)

    def test_cooldown_ms_positive(self):
        self.assertGreater(_RESTART_COOLDOWN_MS, 0)

    def test_config_files_is_frozenset(self):
        self.assertIsInstance(_CONFIG_FILES, frozenset)
        self.assertIn("config.toml", _CONFIG_FILES)


def _make_bare_watcher(**overrides):
    """Create a bare ConfigWatcher bypassing __init__ (slots-safe)."""
    with mock.patch.object(ConfigWatcher, "__init__", lambda self: None):
        w = ConfigWatcher.__new__(ConfigWatcher)
    defaults = dict(
        watched_names={"config.toml"},
        _file_hashes={},
        _restart_pending=False,
        _restart_timer_id=None,
        _restart_delay=_DEFAULT_RESTART_DELAY,
        _last_restart_at_us=0,
        _cooldown_timer_id=None,
        monitors=[],
    )
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(w, k, v)
    return w


class ConfigWatcherHashTest(unittest.TestCase):
    """Test _read_file_hash with real temp files."""

    def setUp(self):
        fd, self._path = tempfile.mkstemp()
        with os.fdopen(fd, "wb") as f:
            f.write(b"test content")

    def tearDown(self):
        os.unlink(self._path)

    def test_hash_matches_sha256(self):
        w = _make_bare_watcher()
        result = w._read_file_hash(self._path)
        expected = hashlib.sha256(b"test content").hexdigest()
        self.assertEqual(result, expected)

    def test_same_content_same_hash(self):
        w = _make_bare_watcher()
        h1 = w._read_file_hash(self._path)
        h2 = w._read_file_hash(self._path)
        self.assertEqual(h1, h2)

    def test_missing_file_returns_none(self):
        w = _make_bare_watcher()
        result = w._read_file_hash("/nonexistent/file.txt")
        self.assertIsNone(result)


class ConfigWatcherRestartDelayTest(unittest.TestCase):
    """Test _get_restart_delay with various config values."""

    def _make_watcher(self):
        with mock.patch.object(ConfigWatcher, "__init__", lambda self: None):
            return ConfigWatcher.__new__(ConfigWatcher)

    def test_default_delay(self):
        w = self._make_watcher()
        with mock.patch("utils.config_watcher.tsumiki_config", {}):
            self.assertEqual(w._get_restart_delay(), _DEFAULT_RESTART_DELAY)

    def test_custom_delay(self):
        w = self._make_watcher()
        cfg = {"general": {"restart_delay": 500}}
        with mock.patch("utils.config_watcher.tsumiki_config", cfg):
            self.assertEqual(w._get_restart_delay(), 500)

    def test_none_delay_uses_default(self):
        w = self._make_watcher()
        cfg = {"general": {"restart_delay": None}}
        with mock.patch("utils.config_watcher.tsumiki_config", cfg):
            self.assertEqual(w._get_restart_delay(), _DEFAULT_RESTART_DELAY)

    def test_invalid_delay_uses_default(self):
        w = self._make_watcher()
        cfg = {"general": {"restart_delay": "bad"}}
        with mock.patch("utils.config_watcher.tsumiki_config", cfg):
            self.assertEqual(w._get_restart_delay(), _DEFAULT_RESTART_DELAY)


class ConfigWatcherOnFileChangedTest(unittest.TestCase):
    """Test _on_file_changed event filtering with real temp files."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._path_a = os.path.join(self._tmpdir, "config.toml")
        with open(self._path_a, "wb") as f:
            f.write(b"content_a")
        self._path_b = os.path.join(self._tmpdir, "other.toml")
        with open(self._path_b, "wb") as f:
            f.write(b"content_b")

    def tearDown(self):
        os.unlink(self._path_a)
        os.unlink(self._path_b)
        os.rmdir(self._tmpdir)

    def _make_file_mock(self, path):
        m = mock.Mock()
        m.get_path.return_value = path
        m.get_basename.return_value = os.path.basename(path)
        return m

    def test_ignores_non_done_hint_event(self):
        w = _make_bare_watcher()
        file_mock = self._make_file_mock(self._path_a)
        w._on_file_changed(None, file_mock, None, "CHANGED")
        self.assertFalse(w._restart_pending)

    def test_ignores_unwatched_files(self):
        w = _make_bare_watcher()
        file_mock = self._make_file_mock(self._path_b)
        with mock.patch(
            "utils.config_watcher.Gio.FileMonitorEvent.CHANGES_DONE_HINT",
            _DONE_HINT,
        ):
            w._on_file_changed(None, file_mock, None, _DONE_HINT)
        self.assertFalse(w._restart_pending)

    def test_same_hash_does_not_trigger(self):
        w = _make_bare_watcher()
        h = w._read_file_hash(self._path_a)
        w._file_hashes[self._path_a] = h
        file_mock = self._make_file_mock(self._path_a)
        with mock.patch(
            "utils.config_watcher.Gio.FileMonitorEvent.CHANGES_DONE_HINT",
            _DONE_HINT,
        ):
            w._on_file_changed(None, file_mock, None, _DONE_HINT)
        self.assertFalse(w._restart_pending)

    def test_different_hash_triggers_restart(self):
        w = _make_bare_watcher()
        w._file_hashes[self._path_a] = "old_hash"
        file_mock = self._make_file_mock(self._path_a)
        with (
            mock.patch(
                "utils.config_watcher.Gio.FileMonitorEvent.CHANGES_DONE_HINT",
                _DONE_HINT,
            ),
            mock.patch("utils.config_watcher.GLib.timeout_add"),
        ):
            w._on_file_changed(None, file_mock, None, _DONE_HINT)
        self.assertTrue(w._restart_pending)

    def test_already_pending_skips_timer(self):
        w = _make_bare_watcher(_restart_pending=True)
        file_mock = self._make_file_mock(self._path_a)
        with (
            mock.patch(
                "utils.config_watcher.Gio.FileMonitorEvent.CHANGES_DONE_HINT",
                _DONE_HINT,
            ),
            mock.patch("utils.config_watcher.GLib.timeout_add") as mock_timeout,
        ):
            w._on_file_changed(None, file_mock, None, _DONE_HINT)
        mock_timeout.assert_not_called()


class ConfigWatcherStopTest(unittest.TestCase):
    """Test stop cleans up monitors and timers."""

    def test_stop_clears_state(self):
        mock_monitor = mock.Mock()
        w = _make_bare_watcher(
            monitors=[mock_monitor],
            _file_hashes={"/tmp/config.toml": "abc"},
            _restart_timer_id=42,
            _cooldown_timer_id=99,
        )
        with mock.patch("utils.config_watcher.GLib.source_remove") as rm:
            w.stop()

        mock_monitor.cancel.assert_called_once()
        self.assertEqual(w.monitors, [])
        self.assertEqual(w._file_hashes, {})
        self.assertIsNone(w._restart_timer_id)
        self.assertIsNone(w._cooldown_timer_id)
        self.assertEqual(rm.call_count, 2)


class StartStopConfigWatchingTest(unittest.TestCase):
    """Test the module-level start/stop lifecycle functions."""

    def setUp(self):
        import utils.config_watcher as cw

        cw._watcher = None

    def tearDown(self):
        import utils.config_watcher as cw

        cw._watcher = None

    def test_start_creates_watcher(self):
        with mock.patch("utils.config_watcher.ConfigWatcher") as mock_cw:
            start_config_watching()
            mock_cw.assert_called_once()

    def test_start_is_idempotent(self):
        with mock.patch("utils.config_watcher.ConfigWatcher") as mock_cw:
            start_config_watching()
            start_config_watching()
            self.assertEqual(mock_cw.call_count, 1)

    def test_stop_clears_watcher(self):
        import utils.config_watcher as cw

        mock_watcher = mock.Mock()
        cw._watcher = mock_watcher

        stop_config_watching()
        mock_watcher.stop.assert_called_once()
        self.assertIsNone(cw._watcher)

    def test_stop_when_none_is_noop(self):
        stop_config_watching()


if __name__ == "__main__":
    unittest.main()

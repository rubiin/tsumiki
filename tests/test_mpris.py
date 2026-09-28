import unittest
from unittest import mock

try:
    import gi

    gi.require_version("Playerctl", "2.0")
    from services.mpris import MprisPlayer

    HAS_PLAYERCTL = True
except ImportError:  # playerctl library / bindings unavailable
    HAS_PLAYERCTL = False


try:
    from widgets.mpris import MprisWidget

    HAS_MPRIS_WIDGET = True
except (ImportError, ValueError):  # GTK / fabric widgets unavailable
    HAS_MPRIS_WIDGET = False

from tests.helpers import bare_quotes


@unittest.skipUnless(HAS_PLAYERCTL, "Playerctl bindings unavailable")
class MprisPlayerSafetyTest(unittest.TestCase):
    """Our getters must never call into a dead player."""

    def _make_player(self, name: str = "no-such-player") -> MprisPlayer:
        raw = mock.Mock()
        raw.get_property.return_value = name
        player = MprisPlayer(raw)
        player._player = None  # simulate exit without touching the bus
        return player

    def test_getters_return_defaults_when_player_gone(self):
        player = self._make_player()
        self.assertEqual(player.metadata, {})
        self.assertEqual(player.title, "")
        self.assertEqual(player.artist, "")
        self.assertEqual(player.playback_status, "unknown")
        self.assertEqual(player.position, 0)
        self.assertFalse(player.can_pause)
        self.assertFalse(player.can_go_next)

    def test_unowned_name_never_reaches_playerctl(self):
        raw = mock.Mock()
        raw.get_property.return_value = "definitely-not-a-real-player-zzz"
        player = MprisPlayer(raw)
        player._player = None  # simulate exit without touching the bus

        self.assertEqual(player.metadata, {})
        self.assertEqual(player.title, "")
        self.assertEqual(player.artist, "")

        # With _player None, getters must not touch the raw playerctl proxy.
        self.assertEqual(raw.get_property.call_count, 0)


@unittest.skipUnless(HAS_PLAYERCTL, "Playerctl bindings unavailable")
class MprisCoalescingTest(unittest.TestCase):
    """One player signal must cost one main-loop wakeup and one ``changed``.

    Players re-emit ``metadata`` about once a second while playing, so a
    callback per property turned a 1 Hz event into a ~10 Hz storm.
    """

    class _FakePlayer:
        def __init__(self):
            self.properties = {
                "metadata": {
                    "mpris:artUrl": "file:///art.png",
                    "mpris:length": 200000000,
                },
                "playback_status": 2,
                "loop_status": 0,
                "shuffle": False,
                "can_go_next": True,
                "can_go_previous": True,
                "can_seek": True,
                "can_pause": True,
                "position": 0,
                "player-name": "fake",
            }
            self.handlers: dict[str, object] = {}

        def connect(self, name, callback):
            self.handlers[name] = callback
            return len(self.handlers)

        def get_property(self, name):
            return self.properties.get(name)

        def get_title(self):
            return "Track"

        def get_artist(self):
            return "Artist"

        def get_album(self):
            return "Album"

    class _ImmediateGLib:
        """Runs idle callbacks inline and counts the main-loop wakeups."""

        PRIORITY_DEFAULT_IDLE = 200

        def __init__(self):
            self.idle_calls = 0

        def idle_add(self, callback, *args, priority=None):
            self.idle_calls += 1
            callback(*args)
            return 1

    def setUp(self):
        self.raw = self._FakePlayer()
        self.glib = self._ImmediateGLib()
        patcher = mock.patch("services.mpris.GLib", self.glib)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.player = MprisPlayer(self.raw)
        self.changed: list = []
        self.notified: list[str] = []
        self.player.connect("changed", lambda *_: self.changed.append(True))
        self.player.connect(
            "notify", lambda _obj, pspec: self.notified.append(pspec.name)
        )
        # Discard the startup pass; it is asserted separately.
        self.changed.clear()
        self.notified.clear()
        self.idle_calls = self.glib.idle_calls

    def _metadata_event(self):
        self.raw.handlers["metadata"](self.raw)
        return self.glib.idle_calls - self.idle_calls

    def test_one_metadata_signal_is_one_idle_callback(self):
        self.assertEqual(1, self._metadata_event())

    def test_one_metadata_signal_emits_one_changed(self):
        self._metadata_event()

        self.assertEqual(1, len(self.changed))

    def test_every_property_the_widget_listens_to_is_notified(self):
        self._metadata_event()

        # Exactly the signals widgets/mpris.py and shared/media.py connect to.
        for prop in ("metadata", "title", "arturl", "length", "can-pause"):
            self.assertIn(prop, self.notified)

    def test_an_unchanged_repeat_notifies_nothing_a_second_time(self):
        self._metadata_event()
        self.notified.clear()

        self._metadata_event()

        self.assertEqual([], self.notified)
        self.assertEqual(2, len(self.changed), "one changed per event is kept")

    def test_a_new_track_notifies_again(self):
        self._metadata_event()
        self.raw.properties["metadata"] = {"mpris:length": 300000000}
        self.notified.clear()

        self._metadata_event()

        self.assertIn("metadata", self.notified)

    def test_the_startup_pass_emits_one_changed_not_one_per_property(self):
        self.player.update_status_once()

        self.assertEqual(1, len(self.changed))
        self.assertGreater(len(self.notified), 5)

    def test_a_single_player_signal_path_still_notifies_and_emits(self):
        self.player.notifier("playback-status")

        self.assertEqual(["playback-status"], self.notified)
        self.assertEqual(1, len(self.changed))

    def test_a_dead_player_notifies_nothing(self):
        self.player._player = None

        self.player.update_status()
        self.player.notifier("title")

        self.assertEqual([], self.notified)
        self.assertEqual([], self.changed)


@unittest.skipUnless(HAS_MPRIS_WIDGET, "mpris widget unavailable")
class MprisProgressFillTest(unittest.TestCase):
    """The fill must be sized through the geometry API, never recompiled CSS."""

    def _make_widget(self, position, length=200, alloc_width=100):
        widget = MprisWidget.__new__(MprisWidget)
        widget.meta_box = mock.Mock()
        widget.progress = mock.Mock()
        widget.progress.get_allocated_width.return_value = alloc_width
        widget.progress_fill = mock.Mock()
        widget._last_progress_pct = None
        widget._last_fill_px = 0
        widget.player = mock.Mock(
            playback_status="playing", length=length, position=position, title="Track"
        )
        return widget

    def test_unchanged_progress_does_not_reapply_the_width(self):
        widget = self._make_widget(position=20)

        for _ in range(10):
            widget._update_progress()

        # 20/200 -> 10% of 100px, applied once and then left alone.
        widget.progress_fill.set_size_request.assert_called_once_with(10, -1)

    def test_changed_progress_reapplies_the_width(self):
        widget = self._make_widget(position=20)
        widget._update_progress()
        widget.player.position = 100

        widget._update_progress()

        widget.progress_fill.set_size_request.assert_called_with(50, -1)

    def test_fill_never_uses_a_css_min_width(self):
        widget = self._make_widget(position=20)

        widget._update_progress()

        widget.progress_fill.set_style.assert_not_called()

    def test_hidden_progress_clears_the_fill_once(self):
        widget = self._make_widget(position=20)
        widget._update_progress()
        widget.player.playback_status = "stopped"
        widget.player.title = ""

        for _ in range(5):
            widget._update_progress()

        widget.progress_fill.set_size_request.assert_called_with(0, -1)
        widget.progress.set_visible.assert_called_with(False)


@unittest.skipUnless(HAS_MPRIS_WIDGET, "mpris widget unavailable")
class MprisProgressTimerTest(unittest.TestCase):
    """The 1 Hz progress tick must only run while playback advances."""

    def _make_widget(self, status):
        """Build an MprisWidget without touching GTK widget init."""
        widget = MprisWidget.__new__(MprisWidget)
        widget.exit = False
        widget.player = mock.Mock(playback_status=status)
        widget._start_progress_timer = mock.Mock()
        widget._stop_progress_timer = mock.Mock()
        return widget

    def test_tick_runs_only_while_playing(self):
        for status, starts in (
            ("playing", True),
            ("paused", False),
            ("stopped", False),
            (None, False),
        ):
            with self.subTest(status=status):
                widget = self._make_widget(status)

                widget._sync_progress_timer(status)

                self.assertIs(widget._start_progress_timer.called, starts)
                self.assertIs(widget._stop_progress_timer.called, not starts)

    def test_get_current_stops_tick_when_nothing_plays(self):
        widget = self._make_widget("stopped")
        widget._set_default_values = mock.Mock()

        widget.get_current()

        widget._stop_progress_timer.assert_called_once()
        widget._start_progress_timer.assert_not_called()

    def test_get_current_starts_tick_while_playing(self):
        widget = self._make_widget("playing")
        widget.label = mock.Mock()
        widget.label_format = "{title}"
        widget.default_cover = "/tmp/cover.png"
        widget.show = mock.Mock()
        widget._set_artwork = mock.Mock()
        widget._update_progress = mock.Mock()
        widget.set_tooltip_if_enabled = mock.Mock()
        widget.player.title = "Track"
        widget.player.artist = "Artist"
        widget.player.album = "Album"
        widget.player.player_name = "Player"
        widget.player.arturl = None

        widget.get_current()

        widget._start_progress_timer.assert_called_once()
        widget._stop_progress_timer.assert_not_called()

    def test_vanished_player_with_no_fallback_stops_the_tick(self):
        widget = self._make_widget("playing")
        widget.player.player_name = "vlc"
        widget.config = {"ignore": []}
        widget.mpris_manager = mock.Mock(players=[])
        widget._unbind_player_updates = mock.Mock()
        widget._set_default_values = mock.Mock()

        widget.on_player_vanished(None, "vlc")

        widget._stop_progress_timer.assert_called_once()
        self.assertIsNone(widget.player)

    def test_vanished_player_falls_back_to_the_remaining_player(self):
        widget = self._make_widget("playing")
        widget.player.player_name = "vlc"
        fallback = mock.Mock()
        fallback.props.player_name = "mpd"
        widget.config = {"ignore": []}
        widget.mpris_manager = mock.Mock(players=[fallback])
        widget._unbind_player_updates = mock.Mock()
        widget._set_player = mock.Mock()

        widget.on_player_vanished(None, "vlc")

        # _set_player -> get_current re-evaluates the tick for the new player.
        widget._set_player.assert_called_once_with(fallback)


@unittest.skipUnless(HAS_MPRIS_WIDGET, "mpris widget unavailable")
class MprisArtworkTeardownTest(unittest.TestCase):
    """The destroy signal must unbind the player and drop the temp download."""

    def _make_widget(self, temp_path):
        widget = MprisWidget.__new__(MprisWidget)
        widget.exit = False
        widget.player = mock.Mock()
        widget._player_update_handlers = []
        widget._last_temp_art_path = temp_path
        widget._progress_timer_id = 5
        widget._stop_progress_timer = mock.Mock()
        widget._unbind_player_updates = mock.Mock()
        return widget

    def test_destroy_stops_the_tick_unbinds_and_removes_the_temp_file(self):
        widget = self._make_widget("/tmp/cover.png")

        with (
            mock.patch("widgets.mpris.os.path.exists", return_value=True),
            mock.patch("widgets.mpris.os.remove") as remove,
        ):
            MprisWidget._on_destroy(widget)

        widget._stop_progress_timer.assert_called_once()
        widget._unbind_player_updates.assert_called_once()
        remove.assert_called_once_with("/tmp/cover.png")
        self.assertIsNone(widget._last_temp_art_path)
        self.assertTrue(widget.exit)

    def test_destroy_is_safe_without_a_temp_download(self):
        widget = self._make_widget(None)

        with mock.patch("widgets.mpris.os.remove") as remove:
            MprisWidget._on_destroy(widget)

        remove.assert_not_called()

    def test_a_quoted_artwork_path_stays_valid_css(self):
        widget = self._make_widget(None)
        widget.cover = mock.Mock()
        widget.default_cover = "/fallback.png"

        with (
            mock.patch("widgets.mpris.os.path.isfile", return_value=True),
            mock.patch("shared.media.os.path.isfile", return_value=True),
        ):
            MprisWidget._update_art(widget, "/music/Bob's cover.jpg")

        style = widget.cover.set_style.call_args[0][0]
        self.assertIn("/music/Bob\\'s cover.jpg", style)
        self.assertEqual(2, bare_quotes(style))


if __name__ == "__main__":
    unittest.main()

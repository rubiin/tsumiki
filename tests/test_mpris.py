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


if __name__ == "__main__":
    unittest.main()

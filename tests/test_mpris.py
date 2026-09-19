import unittest
from unittest import mock

try:
    import gi

    gi.require_version("Playerctl", "2.0")
    from services.mpris import MprisPlayer

    HAS_PLAYERCTL = True
except ImportError:  # playerctl library / bindings unavailable
    HAS_PLAYERCTL = False


@unittest.skipUnless(HAS_PLAYERCTL, "Playerctl bindings unavailable")
class MprisPlayerSafetyTest(unittest.TestCase):
    """Playerctl's sync getters abort the process (g_error) when the
    player's DBus name is gone - e.g. while VLC restarts its MPRIS service
    on media change. Our getters must never call into a dead player.
    """

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

        # When _player is None, getters must not call back into the raw
        # playerctl proxy at all.
        self.assertEqual(raw.get_property.call_count, 0)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest import mock

try:
    import gi

    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf

    from shared import media as media_module
    from shared.media import (
        _LIGHT_ART_LUMINANCE_THRESHOLD,
        PlayerBoxStack,
        _average_luminance,
    )

    HAS_GDKPIXBUF = True
except (ImportError, ValueError):
    HAS_GDKPIXBUF = False


@unittest.skipUnless(HAS_GDKPIXBUF, "GdkPixbuf bindings unavailable")
class AverageLuminanceTest(unittest.TestCase):
    """Artwork luminance classification for text contrast."""

    def _solid_pixbuf(self, rgba: int) -> GdkPixbuf.Pixbuf:
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 4, 4)
        pixbuf.fill(rgba)
        return pixbuf

    def test_white_image_is_max_luminance(self):
        lum = _average_luminance(self._solid_pixbuf(0xFFFFFFFF))
        self.assertAlmostEqual(lum, 1.0, places=2)
        self.assertGreater(lum, _LIGHT_ART_LUMINANCE_THRESHOLD)

    def test_black_image_is_zero_luminance(self):
        lum = _average_luminance(self._solid_pixbuf(0x00000000))
        self.assertAlmostEqual(lum, 0.0, places=2)
        self.assertLess(lum, _LIGHT_ART_LUMINANCE_THRESHOLD)

    def test_luminance_is_normalized(self):
        lum = _average_luminance(self._solid_pixbuf(0xFFFFFFFF))
        self.assertTrue(0.0 <= lum <= 1.0)

    def test_grayscale_channels_weighted(self):
        # Green channel dominates perceptual luminance (weight 0.7152).
        green = _average_luminance(self._solid_pixbuf(0x00FF00FF))
        blue = _average_luminance(self._solid_pixbuf(0x0000FFFF))
        self.assertGreater(green, blue)

    def test_alpha_only_pixbuf_returns_none(self):
        # Fewer than 3 channels cannot be classified.
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 4, 4)
        pixbuf.fill(0xFFFFFFFF)

        # Simulate a 1-channel buffer by asserting None from a stub.
        class _Stub:
            def get_n_channels(self):
                return 1

        self.assertIsNone(_average_luminance(_Stub()))


@unittest.skipUnless(HAS_GDKPIXBUF, "GdkPixbuf bindings unavailable")
class _FakePlayerStack:
    """Minimal stand-in for the GTK Stack used by PlayerBoxStack."""

    def __init__(self):
        self._children = []
        self.removed = []
        self.visible_child = None

    @property
    def children(self):
        return list(self._children)

    @children.setter
    def children(self, value):
        self._children = list(value)

    def get_children(self):
        return list(self._children)

    def discard(self, box):
        if box in self._children:
            self._children.remove(box)

    def remove(self, box):
        self.discard(box)
        self.removed.append(box)

    def set_visible_child(self, box):
        self.visible_child = box


@unittest.skipUnless(HAS_GDKPIXBUF, "GdkPixbuf bindings unavailable")
class PlayerBoxStackLostPlayerTest(unittest.TestCase):
    """on_lost_player removes the vanished card, falls back, hides when empty."""

    def _make_stack(self, player_names, current=0, section=None):
        """Build a PlayerBoxStack without touching GTK widget init."""
        stack = PlayerBoxStack.__new__(PlayerBoxStack)
        stack.config = {"ignore": []}
        stack.current_stack_pos = current
        stack._section = section
        stack.set_visible = mock.Mock()

        player_stack = _FakePlayerStack()
        for name in player_names:
            box = mock.Mock()
            box.player_name = name
            # GTK's destroy() drops the widget from its parent.
            box.destroy.side_effect = lambda box=box: player_stack.discard(box)
            player_stack.children = [*player_stack.children, box]
        stack.player_stack = player_stack
        return stack

    def _box(self, stack, name):
        for box in stack.player_stack.get_children():
            if box.player_name == name:
                return box
        raise AssertionError(f"box {name!r} not found")

    def test_lost_player_card_is_removed(self):
        stack = self._make_stack(["vlc", "mpd"])
        vlc = self._box(stack, "vlc")

        stack.on_lost_player(mock.Mock(), "vlc")

        vlc.destroy.assert_called_once()
        self.assertIn(vlc, stack.player_stack.removed)

    def test_falls_back_to_remaining_player(self):
        stack = self._make_stack(["vlc", "mpd"], current=0)
        mpd = self._box(stack, "mpd")

        stack.on_lost_player(mock.Mock(), "vlc")

        stack.set_visible.assert_called_once_with(True)
        self.assertIs(stack.player_stack.visible_child, mpd)
        self.assertEqual(stack.current_stack_pos, 0)

    def test_position_clamped_when_visible_player_vanished(self):
        stack = self._make_stack(["vlc", "mpd"], current=1)
        vlc = self._box(stack, "vlc")

        stack.on_lost_player(mock.Mock(), "mpd")

        self.assertEqual(stack.current_stack_pos, 0)
        self.assertIs(stack.player_stack.visible_child, vlc)

    def test_last_player_hides_stack_and_section(self):
        section = mock.Mock()
        stack = self._make_stack(["vlc"], section=section)

        stack.on_lost_player(mock.Mock(), "vlc")

        stack.set_visible.assert_called_once_with(False)
        section.set_visible.assert_called_once_with(False)
        self.assertIsNone(stack.player_stack.visible_child)

    def test_vanished_after_exit_destroy_is_a_safe_noop_for_the_card(self):
        # The player's own exit path may already have destroyed the card
        # before the manager emits player-vanished.
        stack = self._make_stack(["vlc", "mpd"], current=0)
        vlc = self._box(stack, "vlc")
        mpd = self._box(stack, "mpd")
        vlc.destroy()  # simulate the exit-path cleanup

        stack.on_lost_player(mock.Mock(), "vlc")

        mpd.destroy.assert_not_called()
        self.assertIs(stack.player_stack.visible_child, mpd)

    def test_new_player_shows_stack_and_section_again(self):
        section = mock.Mock()
        stack = self._make_stack([], section=section)
        raw_player = mock.Mock()
        raw_player.props.player_name = "mpd"
        raw_player.get_property.return_value = "mpd"
        new_box = mock.Mock()
        new_box.player_name = "mpd"

        with mock.patch.object(media_module, "PlayerBox", return_value=new_box):
            stack.on_new_player(mock.Mock(), raw_player)

        stack.set_visible.assert_called_with(True)
        section.set_visible.assert_called_with(True)
        self.assertIs(stack.player_stack.visible_child, new_box)


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()

"""Tests for the screen-corners window's visibility handling.

The module is an always-on overlay, so it must declare itself visible the way
the dock and desktop clock do. It previously passed ``visible=False`` and then
called ``show_all()`` on the window, which mapped the window and silently
discarded the flag — so the flag lied about what the module wanted.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _has_display() -> bool:
    try:
        from fabric.utils import Gtk

        return bool(Gtk.init_check([])[0])
    except (ImportError, ValueError):
        return False


@unittest.skipUnless(_has_display(), "no display available")
class ScreenCornersVisibilityTest(unittest.TestCase):
    """The window is visible, because an always-on overlay must be."""

    def setUp(self):
        from modules.corners import ScreenCorners

        self.corners = ScreenCorners(
            {"modules": {"screen_corners": {"enabled": True, "size": 20}}}
        )
        self.addCleanup(self.corners.destroy)

    def test_the_window_is_visible(self):
        self.assertTrue(self.corners.get_visible())

    def test_the_corner_shapes_are_shown(self):
        self.assertTrue(self.corners.get_child().get_visible())


class ScreenCornersDeclarationTest(unittest.TestCase):
    """The visible flag is declared, not inferred from a later show_all()."""

    def test_the_window_declares_itself_visible(self):
        from modules.corners import ScreenCorners

        source = (Path(ScreenCorners.__module__.replace(".", "/") + ".py")).read_text()
        self.assertIn("visible=True", source)


if __name__ == "__main__":
    unittest.main()

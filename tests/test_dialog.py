"""Tests for the shared confirmation dialog.

``Dialog.__new__`` caches one instance, so ``__init__`` runs again on every
``Dialog()`` call. Without a guard the second caller re-ran layer-shell setup
and rebuilt the widget tree of a window the application already holds.
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
class DialogSingleInitTest(unittest.TestCase):
    """Only the first Dialog() call may build the window."""

    def setUp(self):
        from shared.dialog import Dialog

        self.dialog_class = Dialog
        self.addCleanup(setattr, Dialog, "_instance", None)

    def test_the_second_caller_reuses_the_first_window(self):
        first = self.dialog_class()
        wrapper, title, buttons = first.wrapper, first.title, first.buttons

        second = self.dialog_class()

        self.assertIs(first, second)
        self.assertIs(first.wrapper, wrapper)
        self.assertIs(first.title, title)
        self.assertIs(first.buttons, buttons)

    def test_the_window_layout_is_built_once(self):
        first = self.dialog_class()
        wrapper = first.wrapper
        children = list(first.get_children())

        second = self.dialog_class()

        self.assertIs(first, second)
        self.assertIs(first.wrapper, wrapper)
        self.assertEqual(children, list(second.get_children()))

    def test_add_content_still_reaches_the_first_window(self):
        dialog = self.dialog_class()

        returned = dialog.add_content("Title", "Body", "true")

        self.assertIs(returned, dialog)
        self.assertEqual("TITLE", dialog.title.get_label())


if __name__ == "__main__":
    unittest.main()

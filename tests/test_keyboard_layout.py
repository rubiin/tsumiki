"""``widgets.keyboard.language_name_map`` overrides the displayed layout name."""

import unittest

from widgets.keyboard_layout import layout_display_name


class LayoutDisplayNameTest(unittest.TestCase):
    """User names win over the built-in short-name map."""

    def test_user_name_overrides_builtin(self):
        names = {"English (US)": "EN"}
        self.assertEqual("EN", layout_display_name("English (US)", names))

    def test_unmapped_layout_falls_back_to_builtin(self):
        names = {"English (US)": "EN"}
        self.assertEqual("DE", layout_display_name("German", names))

    def test_unknown_layout_falls_back_to_raw_name(self):
        self.assertEqual("Klingon", layout_display_name("Klingon", {}))

    def test_no_map_keeps_builtin(self):
        self.assertEqual("US", layout_display_name("English (US)", None))


if __name__ == "__main__":
    unittest.main()

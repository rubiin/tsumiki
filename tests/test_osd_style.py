"""``modules.osd.style`` decides which parts are packed into the OSD.

The style is structural -- what sits in ``#osd-container``, not how it is
painted (that is ``styling.modules.osd.widget_style``). The rule lives in a
pure function so it can be pinned without a display, and so the lockkeys OSD,
which swaps the slider for a label, answers to the same rule.
"""

import unittest

from modules.osd import styled_children


class StyledChildrenTest(unittest.TestCase):
    """Which roles survive each style, and in what order."""

    def setUp(self):
        self.icon, self.scale, self.label = object(), object(), object()

    def parts(self, style: str) -> tuple:
        return styled_children(
            style,
            ("icon", self.icon),
            ("scale", self.scale),
            ("label", self.label),
        )

    def test_default_keeps_everything(self):
        self.assertEqual((self.icon, self.scale, self.label), self.parts("default"))

    def test_compact_drops_the_slider(self):
        self.assertEqual((self.icon, self.label), self.parts("compact"))

    def test_bar_drops_the_icon(self):
        """The strip leads with the slider, so its order is the packed order."""
        self.assertEqual((self.scale, self.label), self.parts("bar"))

    def test_an_unknown_style_degrades_to_the_default(self):
        """A typo must keep the full box, never an empty one."""
        self.assertEqual((self.icon, self.scale, self.label), self.parts("rounded"))

    def test_lockkeys_pairing_is_covered_by_the_same_rule(self):
        """The label role is never hidden, so only the icon can go."""
        lock_label = object()

        self.assertEqual(
            (lock_label,),
            styled_children("bar", ("icon", self.icon), ("label", lock_label)),
        )
        self.assertEqual(
            (self.icon, lock_label),
            styled_children("compact", ("icon", self.icon), ("label", lock_label)),
        )


if __name__ == "__main__":
    unittest.main()

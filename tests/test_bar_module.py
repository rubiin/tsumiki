"""``modules.bar.exclusive`` maps to a layer-shell exclusivity mode."""

import unittest

from modules.bar import bar_exclusivity


class BarExclusivityTest(unittest.TestCase):
    """The default must keep reserving space, as the bar always did."""

    def test_missing_option_keeps_the_old_space_reserving_behavior(self):
        self.assertEqual("auto", bar_exclusivity({}))

    def test_exclusive_true_reserves_space(self):
        self.assertEqual("auto", bar_exclusivity({"exclusive": True}))

    def test_exclusive_false_lets_windows_overlap(self):
        self.assertEqual("none", bar_exclusivity({"exclusive": False}))


if __name__ == "__main__":
    unittest.main()

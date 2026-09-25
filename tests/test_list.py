"""Tests for the batched-list helpers in ``shared/list.py``.

The long lists (clipboard history, notification history, wifi networks) share
the "how many more" arithmetic and the "am I near the end" check.
"""

import unittest
from unittest import mock

from shared.list import ListBox, near_list_end, next_batch_size


class NextBatchSizeTest(unittest.TestCase):
    """The batch count never exceeds what is left."""

    def test_takes_a_full_batch_when_more_remain(self):
        self.assertEqual(8, next_batch_size(loaded=0, total=20, batch_size=8))

    def test_takes_a_partial_batch_at_the_end(self):
        self.assertEqual(3, next_batch_size(loaded=17, total=20, batch_size=8))

    def test_zero_once_exhausted(self):
        self.assertEqual(0, next_batch_size(loaded=20, total=20, batch_size=8))

    def test_zero_when_loaded_past_the_end(self):
        """A shrinking list must not produce a negative slice."""
        self.assertEqual(0, next_batch_size(loaded=25, total=20, batch_size=8))

    def test_zero_for_an_empty_list(self):
        self.assertEqual(0, next_batch_size(loaded=0, total=0, batch_size=8))


class NearListEndTest(unittest.TestCase):
    """Scroll proximity decides when the next batch is built."""

    def _adjustment(self, value, upper, page_size):
        adjustment = mock.Mock()
        adjustment.get_value.return_value = value
        adjustment.get_upper.return_value = upper
        adjustment.get_page_size.return_value = page_size
        return adjustment

    def test_true_near_the_end(self):
        # 460 + 500 = 960, within 50px of the 1000px end.
        adjustment = self._adjustment(value=460, upper=1000, page_size=500)
        self.assertTrue(near_list_end(adjustment, threshold=50))

    def test_false_while_far_from_the_end(self):
        adjustment = self._adjustment(value=0, upper=1000, page_size=100)
        self.assertFalse(near_list_end(adjustment, threshold=50))

    def test_true_exactly_at_the_threshold(self):
        adjustment = self._adjustment(value=450, upper=1000, page_size=500)
        self.assertTrue(near_list_end(adjustment, threshold=50))

    def test_a_larger_threshold_triggers_earlier(self):
        # 910 is 90px from the end: out of reach at 50, inside at 100.
        adjustment = self._adjustment(value=0, upper=1000, page_size=910)
        self.assertFalse(near_list_end(adjustment, threshold=50))
        self.assertTrue(near_list_end(adjustment, threshold=100))

    def test_a_list_that_fits_is_near_its_end(self):
        """No scrollbar means upper == page_size, which must still load."""
        adjustment = self._adjustment(value=0, upper=100, page_size=100)
        self.assertTrue(near_list_end(adjustment, threshold=50))


class ListBoxTest(unittest.TestCase):
    """The helper lives beside the container it feeds."""

    def test_listbox_still_builds(self):
        self.assertIsNotNone(ListBox(name="test-list"))


if __name__ == "__main__":
    unittest.main()

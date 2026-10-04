"""Tests for the calendar toggle on the date/time widget.

Right click on the bar widget flips the date between the Gregorian and the
Nepali (Bikram Sambat) calendar without opening the notification menu, so the
popover is opened from the press instead of from GtkButton's "clicked".
"""

import unittest
from unittest import mock

try:
    from widgets.datetime_menu import DateTimeWidget
    from widgets.extended_datetime import ExtendedDateTime

    HAS_WIDGETS = True
except (ImportError, ValueError):  # GTK / fabric widgets unavailable
    HAS_WIDGETS = False

from utils.constants import DEFAULT_CONFIG


def make_datetime(*, nepali_time: bool = False) -> "ExtendedDateTime":
    """Build an ExtendedDateTime without touching GTK widget init."""
    label = ExtendedDateTime.__new__(ExtendedDateTime)
    label._nepali_time = nepali_time
    label._formatters = ("%Y-%m-%d",)
    label._current_index = 0
    label.set_label = mock.Mock()
    return label


class CalendarDefaultTest(unittest.TestCase):
    """The label starts on the Gregorian calendar, with no config to set."""

    def test_a_fresh_label_is_gregorian(self):
        self.assertFalse(ExtendedDateTime._nepali_time)

    def test_the_widget_config_has_no_calendar_toggle(self):
        self.assertNotIn("nepali_date", DEFAULT_CONFIG["widgets"]["date_time"])

    def test_the_desktop_clock_config_has_no_calendar_toggle(self):
        self.assertNotIn("nepali_date", DEFAULT_CONFIG["modules"]["desktop_clock"])


def make_widget() -> "DateTimeWidget":
    """Build a DateTimeWidget whose date label and popover are mocks."""
    widget = DateTimeWidget.__new__(DateTimeWidget)
    widget.date_label = mock.Mock()
    widget.show_popover = mock.Mock()
    return widget


def press(widget, button: int) -> bool:
    """Deliver a button press carrying *button* to the widget."""
    return widget.on_button_press(None, mock.Mock(button=button))


@unittest.skipUnless(HAS_WIDGETS, "GTK / fabric widgets unavailable")
class CalendarToggleTest(unittest.TestCase):
    """Right click swaps the calendar, left click opens the menu."""

    def test_toggle_calendar_flips_calendar_system(self):
        label = make_datetime()

        self.assertTrue(label.toggle_calendar())
        self.assertTrue(label._nepali_time)
        label.set_label.assert_called_once()

        self.assertFalse(label.toggle_calendar())
        self.assertFalse(label._nepali_time)
        self.assertEqual(label.set_label.call_count, 2)

    def test_formatted_date_differs_between_calendars(self):
        gregorian = make_datetime()
        nepali = make_datetime(nepali_time=True)

        self.assertNotEqual(gregorian.do_format(), nepali.do_format())

    def test_right_click_toggles_calendar_without_opening_the_menu(self):
        widget = make_widget()

        self.assertTrue(press(widget, 3))

        widget.date_label.toggle_calendar.assert_called_once_with()
        widget.show_popover.assert_not_called()

    def test_left_click_opens_the_menu_without_toggling_the_calendar(self):
        widget = make_widget()

        self.assertFalse(press(widget, 1))

        widget.show_popover.assert_called_once_with()
        widget.date_label.toggle_calendar.assert_not_called()

    def test_middle_click_does_nothing(self):
        widget = make_widget()

        self.assertFalse(press(widget, 2))

        widget.show_popover.assert_not_called()
        widget.date_label.toggle_calendar.assert_not_called()

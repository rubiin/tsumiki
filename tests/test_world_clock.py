"""Tests for the world clock's timezone validation and timer alignment.

The widget used to walk the whole zoneinfo database to validate a one- or
two-item config list, and its 60 s repeater started at construction, so the
displayed time could lag the wall clock by up to a minute.
"""

import itertools
import unittest
from datetime import datetime
from unittest import mock

from fabric.utils import GLib

import widgets.world_clock as world_clock
from shared.widget_container import TeardownMixin
from widgets.world_clock import WorldClockWidget


class _ClockProbe(TeardownMixin):
    """The timer bookkeeping on a plain object; no display, no Gtk init."""

    _arm_minute_timer = WorldClockWidget._arm_minute_timer
    _on_minute = WorldClockWidget._on_minute
    _update_ui = WorldClockWidget._update_ui

    def __init__(self):
        self.delays: list[int] = []
        self.clocks: list = []
        self.time_format = "%H:%M"

    def connect(self, *_args) -> int:
        return 0


def _run_at(probe: _ClockProbe, *moments: datetime) -> _ClockProbe:
    """Drive the probe's timer as if the wall clock read *moments* in turn."""
    ids = itertools.count(1)
    with (
        mock.patch("widgets.world_clock.datetime") as clock,
        mock.patch.object(GLib, "timeout_add") as timeout_add,
    ):
        clock.now.side_effect = moments
        timeout_add.side_effect = lambda delay, *_: (
            probe.delays.append(delay) or next(ids)
        )
        for _ in moments:
            probe._arm_minute_timer()
    return probe


def _probe_at(moment: datetime) -> _ClockProbe:
    probe = _ClockProbe()
    _run_at(probe, moment)
    return probe


class InitialRenderTest(unittest.TestCase):
    """The widget must not sit blank waiting for the first minute tick."""

    def test_the_labels_are_filled_before_the_first_timer_fires(self):
        widget = WorldClockWidget()
        self.addCleanup(widget.destroy)

        texts = [label.get_text() for label, _tz in widget.clocks]

        self.assertTrue(texts)
        for text in texts:
            self.assertRegex(text, r"\d{2}:\d{2}:\d{2}")


class MinuteAlignmentTest(unittest.TestCase):
    """The tick lands on a minute boundary, not 60 s from construction."""

    def test_a_fresh_widget_waits_only_for_the_rest_of_the_minute(self):
        probe = _probe_at(datetime(2026, 1, 1, 12, 30, 15))

        self.assertEqual([45_000], probe.delays)

    def test_a_widget_started_at_the_boundary_waits_a_whole_minute(self):
        probe = _probe_at(datetime(2026, 1, 1, 12, 0, 0))

        self.assertEqual([60_000], probe.delays)

    def test_sub_second_remainder_never_produces_a_non_positive_delay(self):
        probe = _probe_at(datetime(2026, 1, 1, 12, 30, 59, 999_000))

        self.assertEqual([1_000], probe.delays)

    def test_a_fired_tick_re_aligns_rather_than_drifting(self):
        """The regression: each tick ran 60 s after the last one, so lag grew."""
        probe = _ClockProbe()
        ids = itertools.count(1)
        fired = datetime(2026, 1, 1, 12, 30, 47)
        with (
            mock.patch("widgets.world_clock.datetime") as clock,
            mock.patch.object(GLib, "timeout_add") as timeout_add,
        ):
            # construction, the redraw read, then the re-arm read
            clock.now.side_effect = [
                datetime(2026, 1, 1, 12, 30, 15),
                fired,
                fired,
            ]
            timeout_add.side_effect = lambda delay, *_: (
                probe.delays.append(delay) or next(ids)
            )

            probe._arm_minute_timer()
            probe._on_minute()

        self.assertEqual([45_000, 13_000], probe.delays)


class TimezoneValidationTest(unittest.TestCase):
    """ZoneInfo raises on an unknown key, so no database scan is needed."""

    def test_the_module_no_longer_scans_the_database(self):
        """The regression: available_timezones() walked ~600 entries."""
        with open(world_clock.__file__) as source:
            self.assertNotIn("available_timezones", source.read())

    def test_an_unknown_key_is_rejected_by_zoneinfo(self):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        with self.assertRaises((ZoneInfoNotFoundError, ValueError)):
            ZoneInfo("Not/AZone")


if __name__ == "__main__":
    unittest.main()

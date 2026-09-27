"""GTK destroys children from C, so a Python ``destroy()`` override never runs.

``gtk_widget_destroy`` recurses into the widget tree and runs dispose on each
child, which emits the ``destroy`` *signal*. It never looks up a Python
``destroy`` override on the way, so any cleanup parked in one keeps running for
the life of the process: a 60 Hz tick, a forked command, a signal handler.

These tests drive the production lifecycle methods on a real ``GObject`` with a
real ``destroy`` signal, torn down by a stand-in parent that only emits the
signal — no display required.
"""

import unittest
from time import monotonic, sleep
from typing import ClassVar
from unittest import mock

import gi

gi.require_version("Gtk", "3.0")
from fabric.utils import GLib  # noqa: E402
from gi.repository import GObject  # noqa: E402

from modules import notification as notification_module  # noqa: E402
from modules.notification import NotificationRevealer, NotificationWidget  # noqa: E402
from shared import sinewave_slider as slider_module  # noqa: E402
from shared import widget_container as container  # noqa: E402
from shared.media import PlayerBox  # noqa: E402
from shared.sinewave_slider import SineWaveSlider  # noqa: E402
from shared.widget_container import TeardownMixin  # noqa: E402
from widgets.custom_widget import CustomWidget, CustomWidgetExecutor  # noqa: E402
from widgets.mpris import MprisWidget  # noqa: E402
from widgets.quick_settings.quick_settings import (  # noqa: E402
    QuickSettingsButtonWidget,
    QuickSettingsMenu,
)
from widgets.volume import VolumeWidget  # noqa: E402

# Every widget whose cleanup used to sit in a destroy() override.
TEARDOWN_OWNERS = [
    CustomWidget,
    MprisWidget,
    NotificationRevealer,
    NotificationWidget,
    PlayerBox,
    QuickSettingsButtonWidget,
    QuickSettingsMenu,
    SineWaveSlider,
    VolumeWidget,
]


class Destroyable(TeardownMixin, GObject.Object):
    """The smallest real GObject TeardownMixin can hang its teardown off."""

    __gsignals__: ClassVar = {"destroy": (GObject.SignalFlags.RUN_LAST, None, ())}


class ParentDestroyedFromC:
    """Stand-in for GTK tearing down a widget tree without a display.

    Only the ``destroy`` signal is emitted; no Python ``destroy`` override is
    dispatched, which is exactly the gap these tests guard.
    """

    def __init__(self, *children):
        self.children = list(children)

    def destroy(self):
        while self.children:
            self.children.pop().emit("destroy")


class _SliderProbe(Destroyable):
    """SineWaveSlider's real animation lifecycle on a signal-capable object."""

    _start_animation = SineWaveSlider._start_animation
    _stop_animation = SineWaveSlider._stop_animation
    _tick = SineWaveSlider._tick
    _on_motion = SineWaveSlider._on_motion

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ticks_armed: list = []
        self.ticks_removed: list[int] = []
        self._morph = 1.0
        self._morph_target = 1.0
        self._morph_speed = 0.15
        self._phase = 0.0
        self._speed = 4
        self._dragging = False
        self.draws = 0

    def add_tick_callback(self, callback):
        self.ticks_armed.append(callback)
        return len(self.ticks_armed)

    def remove_tick_callback(self, tick_id):
        self.ticks_removed.append(tick_id)

    def queue_draw(self):
        self.draws += 1


class _NotificationProbe(Destroyable):
    """NotificationWidget's real expiry timer on a signal-capable object."""

    start_timeout = NotificationWidget.start_timeout
    stop_timeout = NotificationWidget.stop_timeout
    resume_timeout = NotificationWidget.resume_timeout
    _tick = NotificationWidget._tick

    def __init__(self, timeout_ms=3000, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._time_remaining = 0
        self._last_tick_time = 0
        self.progress_timeout = mock.Mock()
        self.closed: list[str] = []
        self.ticks_armed: list = []
        self.ticks_removed: list[int] = []
        self._timeout_ms = timeout_ms

    def get_timeout(self):
        return self._timeout_ms

    def close_notification(self):
        self.closed.append("expired")
        return False

    def add_tick_callback(self, callback):
        self.ticks_armed.append(callback)
        return len(self.ticks_armed)

    def remove_tick_callback(self, tick_id):
        self.ticks_removed.append(tick_id)


class _CustomWidgetProbe(Destroyable):
    """CustomWidget's real destroy-signal cleanup on a signal-capable object."""

    _on_destroy = CustomWidget._on_destroy

    def __init__(self, executor: CustomWidgetExecutor, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._executor = executor
        self.connect("destroy", self._on_destroy)


class GLibRecorder:
    """Patch GLib inside TeardownMixin and record every source it touches."""

    def __init__(self, test: unittest.TestCase):
        self.armed: list[tuple[int, int, object]] = []
        self.removed: list[int] = []
        self.live: set[int] = set()
        self.next_id = 700
        for target, side_effect in (
            ("timeout_add", self._add),
            ("source_remove", self._remove),
        ):
            patcher = mock.patch.object(
                container.GLib, target, side_effect=side_effect
            )
            test.addCleanup(patcher.stop)
            patcher.start()
        patcher = mock.patch.object(
            container, "_source_is_alive", side_effect=self._is_live
        )
        test.addCleanup(patcher.stop)
        patcher.start()

    def _add(self, interval_ms, callback):
        self.next_id += 1
        self.armed.append((interval_ms, self.next_id, callback))
        self.live.add(self.next_id)
        return self.next_id

    def _remove(self, source_id):
        self.removed.append(source_id)
        self.live.discard(source_id)

    def _is_live(self, source_id) -> bool:
        return source_id in self.live

    @property
    def intervals(self) -> list[int]:
        return [interval for interval, _, _ in self.armed]

    def fire(self, index: int = -1) -> bool:
        _, source_id, callback = self.armed[index]
        keep_going = callback()
        if not keep_going:
            self.live.discard(source_id)
        return keep_going


def pump_until(predicate, timeout: float = 5.0) -> bool:
    """Dispatch the real default main loop until *predicate* holds."""
    context = GLib.MainContext.default()
    deadline = monotonic() + timeout
    while not predicate():
        if monotonic() >= deadline:
            return False
        context.iteration(False)
        sleep(0.001)
    return True



class CsideDestroyHarnessTest(unittest.TestCase):
    """The stand-in parent must reproduce the gap, or nothing below means much."""

    def test_a_python_destroy_override_is_never_dispatched(self):
        log: list[str] = []

        class Child(Destroyable):
            def destroy(self):
                log.append("override")

        child = Child()
        child.connect("destroy", lambda *_: log.append("signal"))

        ParentDestroyedFromC(child).destroy()

        self.assertEqual(["signal"], log)


class NoPythonDestroyOverrideTest(unittest.TestCase):
    """Cleanup parked in a destroy() override is cleanup that never happens."""

    def test_no_owned_widget_overrides_destroy(self):
        offenders = [
            cls.__name__ for cls in TEARDOWN_OWNERS if "destroy" in vars(cls)
        ]

        self.assertEqual([], offenders)

    def test_every_widget_with_a_timer_uses_the_tracking_mixin(self):
        # A hand-rolled source id is what TeardownMixin exists to replace.
        with_timers = [
            PlayerBox,
            QuickSettingsMenu,
            SineWaveSlider,
        ]

        self.assertEqual(
            [],
            [cls.__name__ for cls in with_timers if TeardownMixin not in cls.__mro__],
        )


class VolumeWidgetTeardownTest(unittest.TestCase):
    """A leaked speaker handler wakes a dead widget on every volume change."""

    def _make_widget(self, speaker):
        widget = VolumeWidget.__new__(VolumeWidget)
        widget._speaker = speaker
        widget._speaker_volume_handler_id = 7
        return widget

    def test_destroy_cleans_up_the_speaker_handler(self):
        speaker = mock.Mock()
        widget = self._make_widget(speaker)

        # _on_destroy is the "destroy" signal body; a bare __new__ has no signals.
        widget._on_destroy()

        speaker.disconnect.assert_called_once_with(7)
        self.assertIsNone(widget._speaker)
        self.assertIsNone(widget._speaker_volume_handler_id)

    def test_a_widget_that_never_bound_a_speaker_is_a_noop(self):
        widget = VolumeWidget.__new__(VolumeWidget)
        widget._speaker = None
        widget._speaker_volume_handler_id = None

        widget._on_destroy()

        self.assertIsNone(widget._speaker)


class SineWaveSliderTeardownTest(unittest.TestCase):
    """The animation must be a frame-clock tick the frame clock can pause."""

    def setUp(self):
        self.glib = GLibRecorder(self)
        self.slider = _SliderProbe()

    def _arm_drag(self):
        self.slider._dragging = True
        self.slider.do_resolve_style = lambda: {"handle_length": 10}
        self.slider._x_to_value = lambda x, hl: 0.5
        self.slider._throttled_fire_change = lambda: None

    def test_the_animation_is_a_tick_callback_not_a_timeout(self):
        self.slider._start_animation()

        self.assertEqual([], self.glib.intervals, "still on GLib.timeout_add")
        self.assertEqual(1, len(self.slider.ticks_armed))
        self.assertTrue(self.slider._has_tick(slider_module._ANIMATION_TICK))

    def test_unmap_removes_the_tick(self):
        self.slider._start_animation()

        self.slider._stop_animation()

        self.assertEqual([1], self.slider.ticks_removed)
        self.assertFalse(self.slider._has_tick(slider_module._ANIMATION_TICK))

    def test_remapping_does_not_stack_ticks(self):
        self.slider._start_animation()
        self.slider._start_animation()

        self.assertEqual(1, len(self.slider.ticks_armed))

    def test_an_idle_slider_never_arms_a_tick(self):
        self.slider._morph = 0.0
        self.slider._morph_target = 0.0

        self.slider._start_animation()

        self.assertEqual([], self.slider.ticks_armed)

    def test_the_parent_being_destroyed_from_c_removes_the_tick(self):
        self.slider._start_animation()

        ParentDestroyedFromC(self.slider).destroy()

        self.assertEqual([1], self.slider.ticks_removed)
        self.assertEqual({}, self.slider._ticks)

    def test_unmapping_first_keeps_teardown_quiet(self):
        self.slider._start_animation()
        self.slider._stop_animation()

        ParentDestroyedFromC(self.slider).destroy()

        self.assertEqual([1], self.slider.ticks_removed)

    def test_a_drag_does_not_redraw_when_the_tick_already_does(self):
        self.slider._start_animation()
        self._arm_drag()

        self.slider._on_motion(self.slider, mock.Mock(x=50))

        self.assertEqual(0, self.slider.draws)

    def test_a_drag_on_an_idle_slider_still_redraws(self):
        self.slider._morph = 0.0
        self.slider._morph_target = 0.0
        self._arm_drag()

        self.slider._on_motion(self.slider, mock.Mock(x=50))

        self.assertEqual(1, self.slider.draws)


class NotificationExpiryTimerTest(unittest.TestCase):
    """A 2px sliver does not need 60 Hz, and the timer must be tracked."""

    def setUp(self):
        self.glib = GLibRecorder(self)
        self.widget = _NotificationProbe()

    def test_expiry_is_a_timeout_rather_than_a_frame_clock_tick(self):
        self.widget.start_timeout()

        self.assertEqual([], self.widget.ticks_armed)
        self.assertEqual(1, len(self.glib.armed))
        self.assertTrue(
            self.widget._has_timeout(notification_module._EXPIRY_TIMER)
        )

    def test_expiry_runs_at_about_30hz(self):
        self.widget.start_timeout()

        interval = self.glib.intervals[0]
        self.assertGreater(interval, 16, "still vsync-rate, not 30 Hz")
        self.assertLessEqual(interval, 50)
        self.assertAlmostEqual(30, 1000 / interval, delta=2.0)

    def test_the_countdown_survives_the_slower_tick(self):
        """Time comes from the monotonic clock, not from the tick count."""
        self.widget.start_timeout()
        self.widget._time_remaining = 5000
        self.widget._last_tick_time -= 1_000_000  # one second ago

        self.assertTrue(self.widget._tick())

        self.assertAlmostEqual(4000, self.widget._time_remaining, delta=5)

    def test_the_parent_being_destroyed_from_c_removes_the_timer(self):
        self.widget.start_timeout()

        ParentDestroyedFromC(self.widget).destroy()

        self.assertEqual([self.glib.next_id], self.glib.removed)
        self.assertFalse(
            self.widget._has_timeout(notification_module._EXPIRY_TIMER)
        )

    def test_resume_does_not_double_arm(self):
        self.widget.start_timeout()

        self.widget.resume_timeout()

        self.assertEqual(1, len(self.glib.armed))

    def test_expiry_frees_the_key_so_teardown_keeps_quiet(self):
        self.widget.start_timeout()
        self.widget._time_remaining = 0

        self.assertFalse(self.glib.fire())
        self.glib.removed.clear()

        ParentDestroyedFromC(self.widget).destroy()

        self.assertEqual([], self.glib.removed, "removed an already-fired source")


class CustomWidgetTeardownTest(unittest.TestCase):
    """A leaked executor keeps forking `sh -c` forever after a monitor hotplug."""

    def setUp(self):
        self.glib = GLibRecorder(self)
        self.removed: list[int] = []
        patcher = mock.patch(
            "widgets.custom_widget.remove_handler", side_effect=self.removed.append
        )
        self.addCleanup(patcher.stop)
        patcher.start()

        self.executor = CustomWidgetExecutor(
            {"exec": "echo hi", "interval": 1}, mock.Mock()
        )
        self.probe = _CustomWidgetProbe(self.executor)
        self.executor.start()

    def test_the_interval_repeater_is_armed(self):
        self.assertIsNotNone(self.executor._repeater_handler_id)

    def test_the_parent_being_destroyed_from_c_stops_the_commands(self):
        armed_id = self.executor._repeater_handler_id

        ParentDestroyedFromC(self.probe).destroy()

        self.assertEqual([armed_id], self.removed)
        self.assertIsNone(self.executor._repeater_handler_id)
        self.assertTrue(self.executor._destroyed)

    def test_cleanup_releases_the_unix_signal_handler(self):
        self.executor._actual_signal = 34
        self.executor._original_signal_handler = mock.Mock()

        self.probe._on_destroy()

        self.assertIsNone(self.executor._actual_signal)


class OneShotRepeaterTest(unittest.TestCase):
    """A repeater that goes one-shot must not leave a dead id in the list."""

    def setUp(self):
        self.glib = GLibRecorder(self)
        self.widget = Destroyable()

    def test_a_one_shot_repeater_frees_its_key(self):
        self.assertTrue(self.widget._schedule_repeater("tick", 1000, lambda: False))

        self.assertFalse(self.glib.fire())
        self.assertFalse(self.widget._has_timeout("tick"))

    def test_a_still_running_repeater_keeps_its_key(self):
        self.assertTrue(self.widget._schedule_repeater("tick", 1000, lambda: True))

        self.assertTrue(self.glib.fire())
        self.assertTrue(self.widget._has_timeout("tick"))

    def test_a_pending_repeater_blocks_a_second_arm(self):
        self.widget._schedule_repeater("tick", 1000, lambda: True)

        self.assertFalse(self.widget._schedule_repeater("tick", 1000, lambda: True))
        self.assertEqual(1, len(self.glib.armed))

    def test_teardown_removes_a_running_repeater(self):
        self.widget._schedule_repeater("tick", 1000, lambda: True)

        self.widget.emit("destroy")

        self.assertEqual([self.glib.next_id], self.glib.removed)


class TrackedRepeaterListTest(unittest.TestCase):
    """A dead id in the tracked list is a GLib-CRITICAL on every teardown."""

    def setUp(self):
        self.glib = GLibRecorder(self)
        self.widget = Destroyable()

    def test_a_one_shot_repeater_leaves_the_list_when_it_fires(self):
        self.widget._add_repeater(1000, lambda: False)
        self.assertEqual(1, len(self.widget._repeaters))

        self.assertFalse(self.glib.fire())

        self.assertEqual([], self.widget._repeaters)

    def test_a_still_running_repeater_stays_tracked(self):
        self.widget._add_repeater(1000, lambda: True)

        self.assertTrue(self.glib.fire())

        self.assertEqual([self.glib.next_id], self.widget._repeaters)

    def test_a_fired_repeater_is_not_removed_again_at_teardown(self):
        self.widget._add_repeater(1000, lambda: False)
        self.glib.fire()
        self.glib.removed.clear()

        ParentDestroyedFromC(self.widget).destroy()

        self.assertEqual([], self.glib.removed, "removed an already-fired source")

    def test_teardown_still_removes_a_running_repeater(self):
        self.widget._add_repeater(1000, lambda: True)

        ParentDestroyedFromC(self.widget).destroy()

        self.assertEqual([self.glib.next_id], self.glib.removed)

    def test_a_dead_id_is_pruned_when_the_next_repeater_is_registered(self):
        """Re-arming on every keystroke must not accumulate one id per keystroke."""
        self.widget._register_repeater(999)  # an id that is already gone
        self.widget._register_repeater(1234)

        self.assertEqual([1234], self.widget._repeaters)


class RealGlibRepeaterTest(unittest.TestCase):
    """The same guarantees against real sources rather than recorded ones."""

    def setUp(self):
        self.widget = Destroyable()
        self.addCleanup(self.widget.emit, "destroy")

    def test_a_one_shot_repeater_frees_its_id(self):
        self.widget._add_repeater(1, lambda: False)
        self.assertEqual(1, len(self.widget._repeaters))

        self.assertTrue(pump_until(lambda: not self.widget._repeaters))

        self.assertEqual([], self.widget._repeaters)

    def test_a_fired_foreign_id_is_dropped_on_the_next_registration(self):
        fired_id = GLib.timeout_add(1, lambda: False)
        self.widget._register_repeater(fired_id)
        self.assertTrue(
            pump_until(lambda: not container._source_is_alive(fired_id)),
            "the one-shot never fired",
        )

        self.widget._register_repeater(999_999)

        self.assertEqual([999_999], self.widget._repeaters)


if __name__ == "__main__":
    unittest.main()

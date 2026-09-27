from functools import partial

from fabric.utils import GLib
from fabric.widgets.scale import Scale

from ..animator import cubic_bezier
from ..widget_container import BaseWidget


class AnimatedScale(Scale, BaseWidget):
    """A widget to display a scale with animated transitions."""

    def __init__(self, name, curve, duration=0.8, **kwargs):
        super().__init__(name=name, **kwargs)
        self.curve = curve
        self.duration = duration
        self.animator = None
        self._pending_value = None
        self._destroyed = False

        self._animation_timeout = None

        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, *_):
        # An animation can outlive the widget; set_value would touch freed memory.
        self._destroyed = True
        if self.animator is not None:
            self.animator.pause()

    def set_notify_value(self, p, *_):
        if self._destroyed or p.value == self.value:
            return
        self.set_value(p.value)

    def _execute_animation(self):
        if self._destroyed:
            return GLib.SOURCE_REMOVE

        if self._pending_value is not None:
            target_value = self._pending_value
            self._pending_value = None
            self._animation_timeout = None

            if abs(self.value - target_value) > 0.5:
                self.animator.pause()
                self.animator.min_value = self.value
                self.animator.max_value = target_value
                self.animator.play()
            else:
                self.set_value(target_value)

        return GLib.SOURCE_REMOVE

    def animate_value(self, value: float):
        from ..animator import Animator

        self._pending_value = value

        if self.animator is None:
            self.animator = Animator(
                timing_function=partial(cubic_bezier, *self.curve),
                duration=self.duration,
                min_value=self.min_value,
                max_value=self.value,
                tick_widget=self,
                notify_value=self.set_notify_value,
            )

        if self._animation_timeout:
            GLib.source_remove(self._animation_timeout)

        # idle_add, not a timeout: rapid calls cancel the previous idle.
        self._animation_timeout = self._register_repeater(
            GLib.idle_add(self._execute_animation)
        )
        return

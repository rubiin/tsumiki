"""A custom slider widget with a labeled knob that displays the current value.

Draws a trough, filled portion, and a circular knob with centered text.
Supports drag-to-adjust and animated value transitions.
"""

import math

import gi
from fabric.core.service import Signal
from fabric.utils import Gdk, Gtk

from .animator import Animator, cubic_bezier
from .geometry import (
    fraction_from_position,
    rounded_rect_path,
    value_from_fraction,
)
from .widget_container import BaseWidget, TeardownMixin


class LabeledSlider(Gtk.DrawingArea, BaseWidget, TeardownMixin):
    """A slider with a circular knob that shows the current value as a label.

    Emits ``change-value`` with the new float value when the user drags
    or the value is set programmatically via ``set_value``.
    """

    @Signal
    def change_value(self, value: float) -> None: ...

    def __init__(
        self,
        min_value: float = 0,
        max_value: float = 100,
        value: float = 50,
        trough_height: int = 6,
        knob_radius: int = 14,
        format_fn=None,
        orientation="h",
        name="labeled-slider",
        style_classes=None,
        animate=True,
        **kwargs,
    ):
        Gtk.DrawingArea.__init__(self, **kwargs)
        TeardownMixin.__init__(self)

        self.set_name(name)
        if style_classes:
            sc = self.get_style_context()
            if isinstance(style_classes, str):
                sc.add_class(style_classes)
            else:
                for c in style_classes:
                    sc.add_class(c)

        self.min_value = min_value
        self.max_value = max_value
        self._value = value
        self.trough_height = trough_height
        self.knob_radius = knob_radius
        self.format_fn = format_fn or (lambda v: str(round(v)))
        self.orientation = orientation

        self._dragging = False
        self._animate = animate
        self._animator = None
        self._destroyed = False

        self.set_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("button-press-event", self._on_button_press)
        self.connect("button-release-event", self._on_button_release)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("draw", self._on_draw)
        self.connect("destroy", self._on_destroy)

    # ── Value management ────────────────────────────────────────────

    @property
    def value(self):
        return self._value

    def set_value(self, new_value: float, animate: bool | None = None):
        new_value = max(self.min_value, min(self.max_value, new_value))
        if new_value == self._value:
            return

        use_anim = self._animate if animate is None else animate
        if use_anim and not self._dragging:
            self._animate_to(new_value)
        else:
            self._value = new_value
            self.emit("change-value", self._value)
            self.queue_draw()

    def _animate_to(self, target: float):
        if self._destroyed:
            return
        if self._animator is None:
            self._animator = Animator(
                duration=0.3,
                timing_function=lambda p: cubic_bezier(0.25, 0.1, 0.25, 1.0, p),
                min_value=self.min_value,
                max_value=self.max_value,
                tick_widget=self,
            )
            self._animator.connect("notify::value", self._on_animator_step)

        self._animator.min_value = self._value
        self._animator.max_value = target
        self._animator.play()

    def _on_animator_step(self, animator, *_):
        self._value = animator.value
        self.emit("change-value", self._value)
        self.queue_draw()

    # ── Input handling ──────────────────────────────────────────────

    def _value_from_coord(self, x: float, y: float) -> float:
        horizontal = self.orientation == "h"
        alloc = (
            self.get_allocated_width() if horizontal else self.get_allocated_height()
        )
        fraction = fraction_from_position(
            x if horizontal else y, alloc, self.knob_radius + 2
        )
        return value_from_fraction(fraction, self.min_value, self.max_value)

    def _on_button_press(self, _widget, event):
        if event.button == 1:
            self._dragging = True
            if self._animator and self._animator.playing:
                self._animator.pause()
            new_val = self._value_from_coord(event.x, event.y)
            self._value = new_val
            self.emit("change-value", self._value)
            self.queue_draw()
            return True
        return False

    def _on_button_release(self, _widget, event):
        if event.button == 1 and self._dragging:
            self._dragging = False
            return True
        return False

    def _on_motion(self, _widget, event):
        if self._dragging:
            new_val = self._value_from_coord(event.x, event.y)
            self._value = new_val
            self.emit("change-value", self._value)
            self.queue_draw()
            return True
        return False

    # ── Drawing ─────────────────────────────────────────────────────

    def _on_draw(self, _widget, cr):
        sc = self.get_style_context()
        alloc = self.get_allocation()
        width = alloc.width
        height = alloc.height
        radius = self.knob_radius
        padding = radius + 2

        # ── Trough ──
        if self.orientation == "h":
            trough_x = padding
            trough_y = (height - self.trough_height) / 2
            trough_w = max(1, width - 2 * padding)
            trough_h = self.trough_height
        else:
            trough_x = (width - self.trough_height) / 2
            trough_y = padding
            trough_w = self.trough_height
            trough_h = max(1, height - 2 * padding)

        trough_r = self.trough_height / 2

        # Trough background
        self._apply_color(cr, sc, "trough-bg", default="#313244")
        rounded_rect_path(cr, trough_x, trough_y, trough_w, trough_h, trough_r)
        cr.fill()

        # Filled portion
        frac = (self._value - self.min_value) / max(1, self.max_value - self.min_value)
        self._apply_color(cr, sc, "trough-fill", default="#89b4fa")
        if self.orientation == "h":
            fill_w = trough_w * frac
            rounded_rect_path(cr, trough_x, trough_y, fill_w, trough_h, trough_r)
        else:
            fill_h = trough_h * frac
            rounded_rect_path(
                cr,
                trough_x,
                trough_y + trough_h - fill_h,
                trough_w,
                fill_h,
                trough_r,
            )
        cr.fill()

        # ── Knob ──
        if self.orientation == "h":
            knob_x = padding + trough_w * frac
            knob_y = height / 2
        else:
            knob_x = width / 2
            knob_y = padding + trough_h - trough_h * frac

        # Knob shadow
        self._apply_color(cr, sc, "knob-shadow", default="#00000080")
        cr.arc(knob_x, knob_y + 1, radius, 0, 2 * math.pi)
        cr.fill()

        # Knob body
        self._apply_color(cr, sc, "knob-bg", default="#cdd6f4")
        cr.arc(knob_x, knob_y, radius, 0, 2 * math.pi)
        cr.fill()

        # Knob border
        self._apply_color(cr, sc, "knob-border", default="#585b70")
        cr.set_line_width(1.5)
        cr.arc(knob_x, knob_y, radius, 0, 2 * math.pi)
        cr.stroke()

        # Value label
        label = self.format_fn(self._value)
        self._apply_color(cr, sc, "knob-label", default="#11111b")
        font_desc = sc.get_font(Gtk.StateFlags.NORMAL)
        layout = self.create_pango_layout(label)
        layout.set_font_description(font_desc)
        text_w, text_h = layout.get_pixel_size()
        cr.move_to(knob_x - text_w / 2, knob_y - text_h / 2)
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import PangoCairo

        PangoCairo.show_layout(cr, layout)

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _apply_color(cr, sc, css_class, default="#888888"):
        """Try to read a color from the style context; fall back to *default*."""
        # GTK3 doesn't expose per-class colors easily via DrawingArea.
        # We use the base foreground color and rely on SCSS classes for overrides.
        rgba = sc.get_color(Gtk.StateFlags.NORMAL)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)

    def _on_destroy(self, *_):
        self._destroyed = True
        if self._animator is not None:
            self._animator.pause()
            self._animator = None

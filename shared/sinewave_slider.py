import math
from collections.abc import Callable
from typing import Iterable, Literal, TypedDict

from fabric.utils import Gdk, GLib, GObject, Gtk, bulk_connect, cairo
from fabric.widgets.widget import Widget


class SineWaveSliderStyle(TypedDict):
    """Style dictionary for SineWaveSlider."""

    wave_color: Gdk.RGBA
    wave_thickness: float
    amplitude: float
    track_color: Gdk.RGBA
    track_thickness: float
    handle_color: Gdk.RGBA
    handle_thickness: float
    handle_length: float
    handle_corner_radius: float
    gap: float


class SineWaveSlider(Gtk.DrawingArea, Widget):
    """SineWaveSlider: an interactive slider with an animated sine wave, also has
    active and inactive state management

    example CSS:

        #player-slider {
            background-color: transparent;
        }

        #player-slider wave {
            color: rgba(130, 133, 166, 0.9);
            min-width: 4px; /* wave thickness */
            min-height: 3px; /* wave amplitude */
        }

        #player-slider track {
            color: rgba(54, 56, 77, 0.4);
            min-width: 2px; /* track thickness*/
        }

        #player-slider handle {
            color: white;
            min-width: 3px; /* handle thickness*/
            min-height: 22px; /* handle length*/
            margin-left: 5px; /* gap between handle and wave(will be mathematically
              adjusted to look better)*/
            border-radius: 2px; /* handle corner radii*/
        }

    """

    def __init__(
        self,
        value: float = 0.5,
        min_value: float = 0.0,
        max_value: float = 1.0,
        speed: int = 4,
        width: int = 200,
        min_freq: float = 1.0,
        max_freq: float = 6.0,
        active: bool = True,
        on_change: Callable[[float], None] | None = None,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes: Iterable[str] | str | None = None,
        tooltip_text: str | None = None,
        tooltip_markup: str | None = None,
        h_align: (
            Literal["fill", "start", "end", "center", "baseline"] | Gtk.Align | None
        ) = None,
        v_align: (
            Literal["fill", "start", "end", "center", "baseline"] | Gtk.Align | None
        ) = None,
        h_expand: bool = False,
        v_expand: bool = False,
        **kwargs,
    ):
        Gtk.DrawingArea.__init__(self)
        Widget.__init__(
            self,
            name,
            visible,
            all_visible,
            style,
            style_classes,
            tooltip_text,
            tooltip_markup,
            h_align,
            v_align,
            h_expand,
            v_expand,
            None,
            **kwargs,
        )

        self._value = max(min_value, min(max_value, value))
        self._min = min_value
        self._max = max_value
        self._speed = speed
        self._width = width
        self._min_freq = min_freq
        self._max_freq = max_freq
        self._on_change = on_change

        self._phase = 0.0
        self._dragging = False
        self._hover = False

        self._morph = 1.0 if active else 0.0
        self._morph_target = self._morph
        self._morph_speed = 0.15

        # CSS gadget contexts
        self._cached_style: SineWaveSliderStyle | None = None
        self._gadget_classes: dict[Gtk.StyleContext, frozenset[str] | None] = {}
        self._wave_ctx = self.do_create_gadget_context("wave")
        self._track_ctx = self.do_create_gadget_context("track")
        self._handle_ctx = self.do_create_gadget_context("handle")

        self._requested_height = -1
        self.set_size_request(width, 24)

        bulk_connect(
            self,
            {
                "draw": self._on_draw,
                "button-press-event": self._on_press,
                "button-release-event": self._on_release,
                "motion-notify-event": self._on_motion,
                "enter-notify-event": self._on_enter,
                "leave-notify-event": self._on_leave,
                "map": self._start_animation,
                "unmap": self._stop_animation,
            },
        )

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )

        self._anim_id: int | None = None

    # ───────────────────────────────────────── CSS gadget contexts

    def do_create_gadget_context(self, node_name: str) -> Gtk.StyleContext:
        ctx = Gtk.StyleContext()
        ctx.set_parent(self.get_style_context())
        ctx.set_screen(self.get_screen())
        self._gadget_classes[ctx] = None
        ctx.connect("changed", lambda *_: self.do_update_gadget_path(ctx, node_name))
        self.do_update_gadget_path(ctx, node_name)
        return ctx

    def do_update_gadget_path(self, context: Gtk.StyleContext, node_name: str) -> None:
        parent_ctx = self.get_style_context()
        current_classes = frozenset(parent_ctx.list_classes())
        if current_classes != self._gadget_classes[context]:
            self._gadget_classes[context] = current_classes
            new_path = parent_ctx.get_path().copy()
            for cls in list(new_path.iter_list_classes(-1)):
                if cls not in current_classes:
                    new_path.iter_remove_class(-1, cls)
            for cls in current_classes:
                if not new_path.iter_has_class(-1, cls):
                    new_path.iter_add_class(-1, cls)
            new_path.append_type(GObject.TYPE_NONE)
            new_path.iter_set_object_name(-1, node_name)
            context.set_path(new_path)
        context.set_state(self.get_state_flags())
        self._cached_style = None
        self.queue_draw()

    def do_resolve_style(self) -> SineWaveSliderStyle:
        if self._cached_style is not None:
            return self._cached_style

        state = self.get_state_flags()

        self._cached_style = SineWaveSliderStyle(
            wave_color=self._wave_ctx.get_color(state),
            wave_thickness=max(1.0, self._wave_ctx.get_property("min-width", state)),
            amplitude=max(0.0, self._wave_ctx.get_property("min-height", state)),
            track_color=self._track_ctx.get_color(state),
            track_thickness=max(1.0, self._track_ctx.get_property("min-width", state)),
            handle_color=self._handle_ctx.get_color(state),
            handle_thickness=max(
                1.0, self._handle_ctx.get_property("min-width", state)
            ),
            handle_length=max(1.0, self._handle_ctx.get_property("min-height", state)),
            handle_corner_radius=self._handle_ctx.get_property("border-radius", state),
            gap=self._handle_ctx.get_property("margin-left", state),
        )

        needed = int(
            max(
                self._cached_style["amplitude"] * 2
                + self._cached_style["wave_thickness"],
                self._cached_style["handle_length"],
            )
        )
        if needed != self._requested_height:
            self._requested_height = needed
            self.set_size_request(self._width, needed)

        return self._cached_style

    # ───────────────────────────────────────── animation lifecycle

    def _start_animation(self, *_args) -> None:
        if self._anim_id is None and (
            self._morph != self._morph_target or self._morph > 0.0
        ):
            self._anim_id = GLib.timeout_add(16, self._tick)

    def _stop_animation(self, *_args) -> None:
        if self._anim_id is not None:
            GLib.source_remove(self._anim_id)
            self._anim_id = None

    # ───────────────────────────────────────── active state

    def get_active(self) -> bool:
        return self._morph_target == 1.0

    def get_dragging(self) -> bool:
        """Whether the user is currently holding a drag on the slider."""
        return self._dragging

    def set_active(self, active: bool) -> None:
        target = 1.0 if active else 0.0
        if self._morph_target == target:
            return
        self._morph_target = target
        if self.get_mapped():
            self._start_animation()

    # ───────────────────────────────────────── value

    def get_value(self) -> float:
        return self._value

    def set_value(self, value: float) -> None:
        self._value = max(self._min, min(self._max, value))
        self.queue_draw()

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, value: float) -> None:
        self.set_value(value)

    # ───────────────────────────────────────── internals

    def _margin(self, handle_length: float) -> int:
        return int(handle_length // 2 + 4)

    def _value_to_x(self, handle_length: float) -> float:
        width = self.get_allocated_width()
        margin = self._margin(handle_length)
        usable = width - 2 * margin
        if self._max == self._min:
            return margin
        position = (self._value - self._min) / (self._max - self._min)
        return margin + position * usable

    def _x_to_value(self, x: float, handle_length: float) -> float:
        width = self.get_allocated_width()
        margin = self._margin(handle_length)
        usable = width - 2 * margin
        position = (x - margin) / usable
        clamped = max(0.0, min(1.0, position))
        return self._min + clamped * (self._max - self._min)

    def _tick(self) -> bool:
        if self._morph < self._morph_target:
            self._morph = min(self._morph + self._morph_speed, self._morph_target)
        elif self._morph > self._morph_target:
            self._morph = max(self._morph - self._morph_speed, self._morph_target)

        if self._morph > 0.01:
            self._phase += self._speed * 0.01

        self.queue_draw()

        if self._morph <= 0.0 and self._morph_target <= 0.0:
            self._anim_id = None
            return False

        return True

    # ───────────────────────────────────────── draw

    def _on_draw(self, widget: Gtk.Widget, cr: cairo.Context) -> None:
        styles = self.do_resolve_style()

        width = self.get_allocated_width()
        cy = self.get_allocated_height() / 2
        cr.set_antialias(cairo.Antialias.BEST)

        ht = styles["handle_thickness"]
        hl = styles["handle_length"]
        hcr = styles["handle_corner_radius"]
        hc = styles["handle_color"]
        wc = styles["wave_color"]
        wt = styles["wave_thickness"]
        amp = styles["amplitude"]
        tc = styles["track_color"]
        tt = styles["track_thickness"]
        gap = styles["gap"]

        margin = self._margin(hl)
        x_val = self._value_to_x(hl)
        pos = (
            (self._value - self._min) / (self._max - self._min)
            if self._max != self._min
            else 0.0
        )

        # ── track (after handle) ──
        Gdk.cairo_set_source_rgba(cr, tc)
        cr.set_line_width(tt)
        cr.set_line_cap(cairo.LineCap.ROUND)
        cr.move_to(x_val, cy)
        cr.line_to(width - margin, cy)
        cr.stroke()

        # ── sine wave (before handle) ──
        effective_gap = gap + ht / 2
        wave_end = x_val - effective_gap

        if wave_end > margin + 1:
            a = amp * self._morph
            num_cycles = self._min_freq + pos * (self._max_freq - self._min_freq)
            full_width = width - 2 * margin
            k = num_cycles * 2 * math.pi / full_width

            Gdk.cairo_set_source_rgba(cr, wc)
            cr.set_line_width(wt)
            cr.set_line_cap(cairo.LineCap.ROUND)
            cr.set_line_join(cairo.LineJoin.ROUND)

            x = margin
            first = True
            while x <= wave_end:
                y = cy + a * math.sin(k * (x - margin) + self._phase)
                if first:
                    cr.move_to(x, y)
                    first = False
                else:
                    cr.line_to(x, y)
                x += 1.5
            cr.stroke()

        # ── handle ──
        r = min(hcr, ht / 2, hl / 2)
        hx = x_val - ht / 2
        hy = cy - hl / 2

        # shadow
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.15)
        self._rounded_rect(cr, hx + 0.5, hy + 1.5, ht, hl, r)
        cr.fill()

        # main handle
        Gdk.cairo_set_source_rgba(cr, hc)
        self._rounded_rect(cr, hx, hy, ht, hl, r)
        cr.fill()

    def _rounded_rect(
        self, cr: cairo.Context, x: float, y: float, w: float, h: float, r: float
    ) -> None:
        if r <= 0:
            cr.rectangle(x, y, w, h)
            return
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    # ───────────────────────────────────────── min/max

    def set_max(self, max_value: float) -> None:
        self._max = max_value
        self.queue_draw()

    def set_min(self, min_value: float) -> None:
        self._min = min_value
        self.queue_draw()

    # ───────────────────────────────────────── input

    def _on_press(self, widget, event):
        styles = self.do_resolve_style()
        self._dragging = True
        self._value = self._x_to_value(event.x, styles["handle_length"])
        self._fire_change()
        self.queue_draw()

    def _on_release(self, widget, event):
        self._dragging = False

    def _on_motion(self, widget, event):
        if self._dragging:
            styles = self.do_resolve_style()
            self._value = self._x_to_value(event.x, styles["handle_length"])
            self._fire_change()
            self.queue_draw()

    def _on_enter(self, widget: Gtk.Widget, event: Gdk.EventCrossing) -> None:
        self._hover = True
        window = self.get_window()
        if window:
            cursor = Gdk.Cursor.new_for_display(
                Gdk.Display.get_default(), Gdk.CursorType.HAND2
            )
            window.set_cursor(cursor)

    def _on_leave(self, widget: Gtk.Widget, event: Gdk.EventCrossing) -> None:
        self._hover = False
        window = self.get_window()
        if window:
            window.set_cursor(None)

    def _fire_change(self) -> None:
        if self._on_change:
            self._on_change(self._value)

    def destroy(self) -> None:
        self._stop_animation()
        super().destroy()

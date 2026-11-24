from typing import Iterable, Literal

from fabric.core.service import Property
from fabric.utils import GLib, Gtk, cairo
from fabric.widgets.widget import Widget

from .widget_container import BaseWidget

_SCROLL_TICK = "scroll"
_SCROLL_INTERVAL_MS = 16
_SCROLL_STEP_MS = 1000


class Graph(Gtk.DrawingArea, BaseWidget):
    """A scrolling line graph drawn from a live data series.

    Each pushed value scrolls in from the right over one step; the line and
    its fill take their color from the widget's CSS color property.
    """

    @Property(list, "read-write")
    def data(self) -> list:  # type: ignore
        return self._data

    @data.setter
    def data(self, value: list) -> None:
        self._data = value

    def __init__(
        self,
        data: list[float] | None = None,
        min_value: float = 0.0,
        max_value: float = 100.0,
        line_width: float = 2.0,
        fill: bool = True,
        smooth: bool = True,
        dynamic: bool = False,
        size: tuple[int, int] = (200, 100),
        animate_duration: int = 300,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes: Iterable[str] | str | None = None,
        tooltip_text: str | None = None,
        tooltip_markup: str | None = None,
        h_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        v_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        h_expand: bool = False,
        v_expand: bool = False,
        **kwargs,
    ):
        Gtk.DrawingArea.__init__(self)
        Widget.__init__(
            self,
            name=name,
            visible=visible,
            all_visible=all_visible,
            style=style,
            style_classes=style_classes,
            tooltip_text=tooltip_text,
            tooltip_markup=tooltip_markup,
            h_align=h_align,
            v_align=v_align,
            h_expand=h_expand,
            v_expand=v_expand,
            **kwargs,
        )

        self._data = data if data is not None else []
        self._display_data = list(self._data)
        self._min_value = min_value
        self._max_value = max_value
        self._line_width = line_width
        self._fill = fill
        self._smooth = smooth
        self._dynamic = dynamic
        self._animate_duration = animate_duration
        self._scroll_start_time = None
        self._pending: list[float] = []

        self.set_size_request(size[0], size[1])
        self.connect("draw", self._on_draw)

    def push(self, value: float) -> None:
        """Queue *value* to scroll in from the right edge."""
        self._pending.append(value)
        self._data = self._display_data + self._pending
        if not self._has_timeout(_SCROLL_TICK):
            self._scroll_start_time = GLib.get_monotonic_time()
        self._schedule_repeater(_SCROLL_TICK, _SCROLL_INTERVAL_MS, self._tick)

    def _tick(self) -> bool:
        if not self._pending:
            self._scroll_start_time = None
            return False

        elapsed_ms = (GLib.get_monotonic_time() - self._scroll_start_time) / 1000
        if elapsed_ms >= _SCROLL_STEP_MS:
            next_val = self._pending.pop(0)
            self._display_data = [*self._display_data[1:], next_val]
            self._data = self._display_data + self._pending
            self._scroll_start_time = GLib.get_monotonic_time()
            self.queue_draw()
        return True

    def _on_draw(self, widget: Gtk.Widget, cr: cairo.Context) -> None:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        color = self.get_style_context().get_color(Gtk.StateFlags.NORMAL)

        if self._pending and self._scroll_start_time is not None:
            elapsed_ms = (GLib.get_monotonic_time() - self._scroll_start_time) / 1000
            t = min(elapsed_ms / _SCROLL_STEP_MS, 1.0)
            incoming = (
                self._display_data[-1] + (self._pending[0] - self._display_data[-1]) * t
            )
            render_data = [*self._display_data, incoming]
            scroll_frac = t
        else:
            render_data = self._display_data
            scroll_frac = 0.0

        if not render_data or len(render_data) < 2:
            return

        if self._dynamic:
            min_val = min(render_data)
            max_val = max(render_data)
            value_range = max_val - min_val
            min_val -= value_range * 0.1
            max_val += value_range * 0.1
        else:
            min_val = self._min_value
            max_val = self._max_value

        if max_val - min_val == 0:
            max_val = min_val + 1

        num_stable = len(self._display_data)
        x_step = width / (num_stable - 1)
        scroll_offset = x_step * scroll_frac

        def value_to_y(value: float) -> float:
            return height - ((value - min_val) / (max_val - min_val)) * height

        points = [
            (i * x_step - scroll_offset, value_to_y(value))
            for i, value in enumerate(render_data)
        ]

        def draw_curve(
            context: cairo.Context, curve: list[tuple[float, float]]
        ) -> None:
            context.move_to(curve[0][0], curve[0][1])
            if self._smooth and len(curve) > 2:
                for i in range(len(curve) - 1):
                    x0, y0 = curve[i]
                    x1, y1 = curve[i + 1]
                    x_prev, y_prev = curve[i - 1] if i > 0 else (x0, y0)
                    x_next, y_next = curve[i + 2] if i < len(curve) - 2 else (x1, y1)
                    context.curve_to(
                        x0 + (x1 - x_prev) / 6,
                        y0 + (y1 - y_prev) / 6,
                        x1 - (x_next - x0) / 6,
                        y1 - (y_next - y0) / 6,
                        x1,
                        y1,
                    )
            else:
                for x, y in curve[1:]:
                    context.line_to(x, y)

        cr.rectangle(0, 0, width, height)
        cr.clip()
        cr.save()

        if self._fill:
            cr.move_to(0, height)
            cr.line_to(max(points[0][0], 0), points[0][1])
            draw_curve(cr, points)
            cr.line_to(points[-1][0], height)
            cr.line_to(0, height)
            cr.close_path()

            gradient = cairo.LinearGradient(0, height, 0, 0)
            gradient.add_color_stop_rgba(0, color.red, color.green, color.blue, 0.6)
            gradient.add_color_stop_rgba(1, color.red, color.green, color.blue, 0)
            cr.set_source(gradient)
            cr.fill()

        draw_curve(cr, points)
        cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
        cr.set_line_width(self._line_width)
        cr.set_line_cap(cairo.LineCap.ROUND)
        cr.set_line_join(cairo.LineJoin.ROUND)
        cr.stroke()
        cr.restore()

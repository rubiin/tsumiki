import math
from datetime import datetime

import cairo
from fabric.utils import GLib, Gtk
from fabric.widgets.box import Box

from shared.widget_container import BaseWindow, TeardownMixin
from utils.widget_settings import BarConfig
from widgets.extended_datetime import ExtendedDateTime


class CookieClockFace(Gtk.DrawingArea, TeardownMixin):
    """Cookie-style analog clock face inspired by the QML reference."""

    def __init__(self, config: dict):
        super().__init__(name="desktop-clock-cookie-face", visible=True)
        self.sides = int(config.get("cookie_sides", 9))
        self.dial_style = str(config.get("cookie_dial_style", "dots"))
        self.hour_hand_style = str(config.get("cookie_hour_hand_style", "fill"))
        self.minute_hand_style = str(config.get("cookie_minute_hand_style", "medium"))
        self.second_hand_style = str(config.get("cookie_second_hand_style", "dot"))
        self.date_style = str(config.get("cookie_date_style", "bubble"))
        self.show_seconds = bool(config.get("cookie_show_seconds", True))
        self.show_hour_marks = bool(config.get("cookie_show_hour_marks", False))
        self.background_opacity = float(config.get("cookie_background_opacity", 1.0))
        self.widget_scale = float(config.get("cookie_widget_scale", 1.0))
        self.clock_size = int(config.get("cookie_size", 230))

        self._pad = round(30 * self.widget_scale)
        self._scaled_clock_size = round(self.clock_size * self.widget_scale)
        self._cookie_paths: dict = {}

        self.col_background = (0.12, 0.07, 0.13, 1.0)
        self.col_on_background = (0.84, 0.82, 0.86, 0.95)
        self.col_hour_hand = (0.85, 0.62, 0.9, 1.0)
        self.col_minute_hand = (0.95, 0.73, 0.71, 1.0)
        self.col_second_hand = (0.85, 0.62, 0.9, 1.0)
        self.col_background_info = (0.75, 0.72, 0.78, 1.0)
        self.col_tertiary_container = (0.66, 0.08, 0.02, 1.0)
        self.col_on_tertiary_container = (1.0, 1.0, 1.0, 1.0)
        self.col_secondary_container = (0.42, 0.2, 0.45, 1.0)
        self.col_on_secondary_container = (1.0, 1.0, 1.0, 1.0)
        self.col_surface_container_highest = (0.3, 0.22, 0.34, 1.0)
        self.col_on_surface = (1.0, 1.0, 1.0, 1.0)

        self.now = datetime.now()
        tick_interval_ms = 1000 if self.show_seconds else 60000
        self._tick_id = self._register_repeater(
            GLib.timeout_add(tick_interval_ms, self._tick)
        )
        self.set_size_request(
            self._scaled_clock_size + self._pad,
            self._scaled_clock_size + self._pad,
        )
        self.connect("draw", self._on_draw)

    def _tick(self) -> bool:
        self.now = datetime.now()
        self.queue_draw()
        return True

    @staticmethod
    def _draw_badge(cr, x, y, radius, fill, text, font_size):
        cr.set_source_rgba(*fill)
        cr.arc(x, y, radius, 0, 2 * math.pi)
        cr.fill()

        cr.set_source_rgba(1, 1, 1, 1)
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(font_size)
        ext = cr.text_extents(text)
        tx = x - (ext.width / 2 + ext.x_bearing)
        ty = y - (ext.height / 2 + ext.y_bearing)
        cr.move_to(tx, ty)
        cr.show_text(text)

    @staticmethod
    def _draw_centered_text(cr, x, y, text, font_size, color):
        cr.set_source_rgba(*color)
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(font_size)
        ext = cr.text_extents(text)
        tx = x - (ext.width / 2 + ext.x_bearing)
        ty = y - (ext.height / 2 + ext.y_bearing)
        cr.move_to(tx, ty)
        cr.show_text(text)

    def _cookie_path(self, base_radius):
        """The silhouette only depends on the radius, so build it once."""
        path = self._cookie_paths.get(base_radius)
        if path is None:
            path = self._build_cookie_path(base_radius)
            self._cookie_paths[base_radius] = path
        return path

    def _build_cookie_path(self, base_radius):
        # pycairo cannot construct a Path, so build on a scratch context and
        # copy it out; the outline is built once per radius, not once per draw.
        scratch = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
        points = 360
        amplitude = base_radius / 24
        for i in range(points + 1):
            angle = (2 * math.pi * i) / points
            wave = math.sin(angle * self.sides + math.pi / 2) * amplitude
            radius = (base_radius - amplitude) + wave
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            if i == 0:
                scratch.move_to(x, y)
            else:
                scratch.line_to(x, y)
        scratch.close_path()
        return scratch.copy_path()

    def _draw_cookie_shape(self, cr, cx, cy, base_radius):
        cr.new_path()
        # cairo's path is not part of the saved state, so the translate only
        # positions the appended outline and leaves the path behind.
        cr.save()
        cr.translate(cx, cy)
        cr.append_path(self._cookie_path(base_radius))
        cr.restore()

    @staticmethod
    def _draw_round_rect(cr, x, y, width, height, radius):
        r = min(radius, width / 2, height / 2)
        cr.new_sub_path()
        cr.arc(x + width - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + width - r, y + height - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + height - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _draw_shadow(self, cr, cx, cy, cookie_radius):
        if self.background_opacity <= 0:
            return
        for i in range(1, 4):
            cr.new_path()
            self._draw_cookie_shape(cr, cx + i, cy + i, cookie_radius)
            alpha = (0.18 / i) * self.background_opacity
            cr.set_source_rgba(0, 0, 0, alpha)
            cr.fill()

    def _draw_dial_marks(self, cr, cx, cy, radius):
        if self.dial_style == "none":
            return

        mark_radius = radius - round(12 * self.widget_scale)

        if self.dial_style == "dots":
            dot_size = round(6 * self.widget_scale)
            for index in range(12):
                angle = (2 * math.pi * index / 12) - math.pi / 2
                x = cx + mark_radius * math.cos(angle)
                y = cy + mark_radius * math.sin(angle)
                cr.set_source_rgba(*self.col_on_background)
                cr.arc(x, y, dot_size, 0, 2 * math.pi)
                cr.fill()
            return

        if self.dial_style == "numbers":
            marks = [(3, 0), (6, 1), (9, 2), (12, 3)]
            num_radius = radius - round(28 * self.widget_scale)
            for label, idx in marks:
                angle = (2 * math.pi * (idx + 1) / 4) - math.pi / 2
                x = cx + num_radius * math.cos(angle)
                y = cy + num_radius * math.sin(angle)
                self._draw_centered_text(
                    cr,
                    x,
                    y,
                    str(label),
                    round(30 * self.widget_scale),
                    self.col_on_background,
                )
            return

        if self.dial_style == "full":
            cr.set_line_cap(1)
            for index in range(60):
                angle = (2 * math.pi * index / 60) - math.pi / 2
                is_hour = index % 5 == 0
                outer = radius - round(8 * self.widget_scale)
                inner = outer - (
                    round(18 * self.widget_scale)
                    if is_hour
                    else round(7 * self.widget_scale)
                )
                width = (
                    round(4 * self.widget_scale)
                    if is_hour
                    else round(2 * self.widget_scale)
                )
                x1 = cx + inner * math.cos(angle)
                y1 = cy + inner * math.sin(angle)
                x2 = cx + outer * math.cos(angle)
                y2 = cy + outer * math.sin(angle)
                cr.set_source_rgba(*self.col_on_background)
                cr.set_line_width(width)
                cr.move_to(x1, y1)
                cr.line_to(x2, y2)
                cr.stroke()

    def _draw_hour_marks_circle(self, cr, cx, cy):
        if not self.show_hour_marks:
            return

        circle_size = round(135 * self.widget_scale)
        mark_len = round(12 * self.widget_scale)
        mark_width = round(4 * self.widget_scale)

        cr.set_source_rgba(*self.col_on_background)
        cr.arc(cx, cy, circle_size / 2, 0, 2 * math.pi)
        cr.fill()

        for index in range(12):
            angle = (2 * math.pi * index / 12) - math.pi / 2
            outer = circle_size / 2 - round(8 * self.widget_scale)
            inner = outer - mark_len
            x1 = cx + inner * math.cos(angle)
            y1 = cy + inner * math.sin(angle)
            x2 = cx + outer * math.cos(angle)
            y2 = cy + outer * math.sin(angle)
            cr.set_source_rgba(*self.col_background_info)
            cr.set_line_width(mark_width)
            cr.set_line_cap(1)
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.stroke()

    def _draw_rotated_hand(
        self,
        cr,
        cx,
        cy,
        angle,
        length,
        width,
        color,
        style="fill",
        classic=False,
        border=0,
    ):
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(angle)

        x = -round(15 * self.widget_scale) if classic else 0
        y = -width / 2
        radius = round(2 * self.widget_scale) if classic else width / 2
        self._draw_round_rect(cr, x, y, length, width, radius)

        if style == "hollow":
            cr.set_source_rgba(0, 0, 0, 0)
            cr.fill_preserve()
            cr.set_source_rgba(*color)
            cr.set_line_width(border or round(4 * self.widget_scale))
            cr.stroke()
        else:
            cr.set_source_rgba(*color)
            cr.fill()

        cr.restore()

    def _draw_hour_hand(self, cr, cx, cy, angle):
        if self.hour_hand_style == "hide":
            return

        if self.hour_hand_style == "classic":
            self._draw_rotated_hand(
                cr,
                cx,
                cy,
                angle,
                round(72 * self.widget_scale),
                round(8 * self.widget_scale),
                self.col_hour_hand,
                classic=True,
            )
            return

        self._draw_rotated_hand(
            cr,
            cx,
            cy,
            angle,
            round(72 * self.widget_scale),
            round(20 * self.widget_scale),
            self.col_hour_hand,
            style=self.hour_hand_style,
            border=round(4 * self.widget_scale),
        )

    def _draw_minute_hand(self, cr, cx, cy, angle):
        if self.minute_hand_style == "hide":
            return

        width_map = {
            "bold": round(20 * self.widget_scale),
            "medium": round(12 * self.widget_scale),
            "thin": round(5 * self.widget_scale),
            "classic": round(5 * self.widget_scale),
        }
        width = width_map.get(self.minute_hand_style, round(12 * self.widget_scale))
        self._draw_rotated_hand(
            cr,
            cx,
            cy,
            angle,
            round(95 * self.widget_scale),
            width,
            self.col_minute_hand,
            classic=self.minute_hand_style == "classic",
        )

    def _draw_second_hand(self, cr, cx, cy, angle, radius):
        if not self.show_seconds or self.second_hand_style == "hide":
            return

        if self.second_hand_style == "dot":
            dot_size = round(10 * self.widget_scale)
            dot_radius = radius - round(22 * self.widget_scale)
            x = cx + dot_radius * math.cos(angle)
            y = cy + dot_radius * math.sin(angle)
            cr.set_source_rgba(*self.col_second_hand)
            cr.arc(x, y, dot_size, 0, 2 * math.pi)
            cr.fill()
            return

        line_len = round(95 * self.widget_scale)
        line_w = round(2 * self.widget_scale)
        cr.set_source_rgba(*self.col_second_hand)
        cr.set_line_width(line_w)
        cr.set_line_cap(1)
        cr.move_to(cx, cy)
        cr.line_to(
            cx + line_len * math.cos(angle),
            cy + line_len * math.sin(angle),
        )
        cr.stroke()

        if self.second_hand_style == "classic":
            dot_radius = round(40 * self.widget_scale)
            dot_size = round(7 * self.widget_scale)
            x = cx + dot_radius * math.cos(angle)
            y = cy + dot_radius * math.sin(angle)
            cr.arc(x, y, dot_size, 0, 2 * math.pi)
            cr.fill()

    def _draw_date_indicator(self, cr, cx, cy, radius):
        if self.date_style == "hide":
            return

        if self.date_style == "rect":
            rect_w = round(45 * self.widget_scale)
            rect_h = round(30 * self.widget_scale)
            x = cx + radius - rect_w - round(10 * self.widget_scale)
            y = cy - rect_h / 2
            self._draw_round_rect(
                cr,
                x,
                y,
                rect_w,
                rect_h,
                round(6 * self.widget_scale),
            )
            cr.set_source_rgba(*self.col_surface_container_highest)
            cr.fill()
            self._draw_centered_text(
                cr,
                x + rect_w / 2,
                y + rect_h / 2,
                self.now.strftime("%d"),
                round(16 * self.widget_scale),
                self.col_on_surface,
            )
            return

        bubble = round(64 * self.widget_scale) / 2
        self._draw_badge(
            cr,
            cx - radius + bubble,
            cy - radius + bubble,
            bubble,
            self.col_tertiary_container,
            str(self.now.day),
            round(28 * self.widget_scale),
        )
        self._draw_badge(
            cr,
            cx + radius - bubble,
            cy + radius - bubble,
            bubble,
            self.col_secondary_container,
            self.now.strftime("%m"),
            round(28 * self.widget_scale),
        )

    def _on_draw(self, area, cr):
        alloc = area.get_allocation()
        cx = alloc.width / 2
        cy = alloc.height / 2

        cookie_radius = self._scaled_clock_size / 2
        self._draw_shadow(cr, cx, cy, cookie_radius)

        cr.new_path()
        self._draw_cookie_shape(cr, cx, cy, cookie_radius)
        cr.set_source_rgba(
            self.col_background[0],
            self.col_background[1],
            self.col_background[2],
            self.col_background[3] * self.background_opacity,
        )
        cr.fill()

        self._draw_dial_marks(cr, cx, cy, cookie_radius)
        self._draw_hour_marks_circle(cr, cx, cy)

        hour_angle = -math.pi / 2 + (2 * math.pi / 12) * (
            (self.now.hour % 12) + self.now.minute / 60.0
        )
        minute_angle = -math.pi / 2 + (2 * math.pi / 60) * self.now.minute
        second_angle = -math.pi / 2 + (2 * math.pi / 60) * self.now.second

        self._draw_minute_hand(cr, cx, cy, minute_angle)
        self._draw_hour_hand(cr, cx, cy, hour_angle)
        self._draw_second_hand(cr, cx, cy, second_angle, cookie_radius)

        if self.minute_hand_style not in {"bold", "hide"}:
            center_color = (
                self.col_background
                if self.minute_hand_style == "medium"
                else self.col_minute_hand
            )
            cr.set_source_rgba(*center_color)
            cr.arc(cx, cy, round(3 * self.widget_scale), 0, 2 * math.pi)
            cr.fill()

        self._draw_date_indicator(cr, cx, cy, cookie_radius)


class DesktopClock(BaseWindow):
    """Desktop clock widget with classic and cookie variants."""

    def __init__(self, config: BarConfig, **kwargs):
        self.config = config.get("modules", {}).get("desktop_clock", {})
        clock_type = self.config.get("type", "default")

        if clock_type == "cookie":
            child = Box(
                name="desktop-clock-cookie",
                orientation="v",
                h_align="center",
                v_align="center",
                children=[CookieClockFace(self.config)],
            )
        else:
            date_format = self.config.get("date_format", "%Y-%m-%d")

            is_nepali_time = self.config.get("nepali_date", False)

            child = Box(
                name="desktop-clock-box",
                orientation="v",
                children=[
                    ExtendedDateTime(
                        formatters=[self.config.get("time_format", "%H:%M:%S")],
                        nepali_time=is_nepali_time,
                        name="clock",
                    ),
                    ExtendedDateTime(
                        formatters=date_format,
                        nepali_time=is_nepali_time,
                    ),
                ],
            )

        super().__init__(
            name="desktop_clock",
            layer=self.config.get("layer", "overlay"),
            anchor=self.config.get("anchor", "center"),
            child=child,
            **kwargs,
        )

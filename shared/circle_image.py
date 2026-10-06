from typing import Iterable, Literal

from fabric.core.service import Property
from fabric.utils import Gdk, GdkPixbuf, Gtk, cairo, math
from fabric.widgets.widget import Widget

from utils.pixbuf import load_file_pixbuf

from .widget_container import BaseWidget


def circle_geometry(
    alloc_width: int, alloc_height: int, image_width: int, image_height: int
) -> tuple[float, float, float, float]:
    """Return ``(centre_x, centre_y, radius, scale)`` for the drawn circle.

    The circle is inscribed in the allocation, not in the size request, so an
    expanding widget keeps its artwork centred. ``scale`` covers the circle so a
    non-square source is centre-cropped symmetrically instead of being sliced off.
    """
    side = min(alloc_width, alloc_height)
    if side <= 0 or image_width <= 0 or image_height <= 0:
        return 0.0, 0.0, 0.0, 1.0
    return (
        alloc_width / 2,
        alloc_height / 2,
        side / 2,
        max(side / image_width, side / image_height),
    )


class CircularImage(Gtk.DrawingArea, BaseWidget):
    """A widget that displays an image in a circle."""

    @Property(int, "read-write")
    def angle(self) -> int:  # type: ignore
        return self._angle

    @angle.setter
    def angle(self, value: int):
        new_angle = value % 360
        if new_angle != self._angle:
            self._angle = new_angle
            self.queue_draw()

    def __init__(
        self,
        image_file: str | None = None,
        pixbuf: None = None,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
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
        size: Iterable[int] | int | None = None,
        **kwargs,
    ):
        Gtk.DrawingArea.__init__(self)
        Widget.__init__(
            self,
            name=name,
            visible=visible,
            all_visible=all_visible,
            style=style,
            tooltip_text=tooltip_text,
            tooltip_markup=tooltip_markup,
            h_align=h_align,
            v_align=v_align,
            h_expand=h_expand,
            v_expand=v_expand,
            size=size,
            **kwargs,
        )
        self._image_file = image_file
        self._angle = 0
        self.size = size
        self._image: GdkPixbuf.Pixbuf | None = (
            load_file_pixbuf(image_file, size, size)
            if image_file and size
            else pixbuf
            if pixbuf
            else None
        )
        self.connect("draw", self.on_draw)

    def on_draw(self, widget: "CircularImage", ctx: cairo.Context):
        if not self._image:
            return

        # Centre on the allocation and scale to cover: expanding widgets and
        # non-square artwork otherwise get pushed off-centre and sliced lopsided.
        centre_x, centre_y, radius, scale = circle_geometry(
            self.get_allocated_width(),
            self.get_allocated_height(),
            self._image.get_width(),
            self._image.get_height(),
        )
        if radius <= 0:
            return

        ctx.save()
        ctx.arc(centre_x, centre_y, radius, 0, 2 * math.pi)
        ctx.clip()
        ctx.translate(centre_x, centre_y)
        ctx.rotate(self._angle * math.pi / 180.0)
        ctx.scale(scale, scale)
        ctx.translate(
            -self._image.get_width() / 2,
            -self._image.get_height() / 2,
        )
        Gdk.cairo_set_source_pixbuf(ctx, self._image, 0, 0)
        ctx.paint()
        ctx.restore()

    def set_image_from_file(self, new_image_file):
        if new_image_file == "":
            return
        self._image = (
            load_file_pixbuf(new_image_file, -1, self.size) if self.size else None
        )
        self.queue_draw()

    def set_image_from_pixbuf(self, pixbuf):
        if not pixbuf:
            return
        self._image = pixbuf
        self.queue_draw()

    def set_image_size(self, size: Iterable[int] | int):
        if size is Iterable:
            x, y = size
            self._image = self._image.scale_simple(x, y, GdkPixbuf.InterpType.BILINEAR)
        else:
            self._image = self._image.scale_simple(
                size, size, GdkPixbuf.InterpType.BILINEAR
            )
        self.queue_draw()

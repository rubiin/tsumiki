"""An image tile with rounded corners: GTK3 CSS does not clip image content."""

from fabric.utils import Gdk, GdkPixbuf, Gtk, cairo
from fabric.widgets.widget import Widget

from .geometry import rounded_rect_path
from .widget_container import BaseWidget


class RoundedCoverImage(Gtk.DrawingArea, BaseWidget):
    """Draws a pixbuf scaled to cover the allocation, centre-cropped and rounded."""

    def __init__(
        self,
        width: int,
        height: int,
        radius: float = 10,
        name: str | None = None,
    ):
        Gtk.DrawingArea.__init__(self)
        Widget.__init__(self, name=name)
        self._radius = radius
        self._pixbuf: GdkPixbuf.Pixbuf | None = None
        self.set_size_request(width, height)
        self.connect("draw", self._on_draw)
        self.show()

    def set_pixbuf(self, pixbuf: GdkPixbuf.Pixbuf | None):
        self._pixbuf = pixbuf
        self.queue_draw()

    def _on_draw(self, _widget: "RoundedCoverImage", cr: cairo.Context):
        if not self._pixbuf:
            return

        width = self.get_allocated_width()
        height = self.get_allocated_height()
        image_width = self._pixbuf.get_width()
        image_height = self._pixbuf.get_height()
        if min(width, height, image_width, image_height) <= 0:
            return

        scale = max(width / image_width, height / image_height)

        cr.save()
        rounded_rect_path(cr, 0, 0, width, height, self._radius)
        cr.clip()
        cr.translate(
            (width - image_width * scale) / 2,
            (height - image_height * scale) / 2,
        )
        cr.scale(scale, scale)
        Gdk.cairo_set_source_pixbuf(cr, self._pixbuf, 0, 0)
        cr.paint()
        cr.restore()

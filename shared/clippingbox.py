from typing import cast

from fabric.utils import cairo
from fabric.widgets.box import Box

from .geometry import rounded_rect_path


class ClippingBox(Box):
    """A regular `Box` that replicates the CSS behavior of `overflow: hidden`
    because GTK failed at it.

    NOTE: use instead of the old `CustomImage` snippet.
    """

    @staticmethod
    def render_shape(cr: cairo.Context, width: int, height: int, radius: int = 0):
        rounded_rect_path(cr, 0, 0, width, height, radius)
        return cr.close_path()

    def do_draw(self, cr: cairo.Context):
        cr.save()
        ClippingBox.render_shape(
            cr,
            self.get_allocated_width(),
            self.get_allocated_height(),
            cast(
                int,
                self.get_style_context().get_property(
                    "border-radius", self.get_state_flags()
                ),
            ),
        )
        cr.clip()

        Box.do_draw(self, cr)

        cr.restore()
        return True

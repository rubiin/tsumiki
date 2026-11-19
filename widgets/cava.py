from fabric.utils import exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.label import Label

import utils.functions as helpers
from services import cava_service
from shared.widget_container import ButtonWidget
from utils.constants import BAR_GLYPHS
from utils.functions import safe_disconnect


def bars_to_glyphs(values, glyphs: str = BAR_GLYPHS) -> str:
    """Render normalised bar levels (0.0-1.0) as block characters."""
    last = len(glyphs) - 1
    return "".join(glyphs[min(last, int(value * len(glyphs)))] for value in values)


class CavaWidget(ButtonWidget):
    """A widget to display cava audio levels from the shared cava service."""

    def __init__(self, **kwargs):
        super().__init__(name="cava", **kwargs)

        helpers.check_executable_exists("cava")

        color = self.config.get("color", "#ffffff")  # default white
        if not helpers.is_valid_gjs_color(color):
            raise ValueError(f"Invalid color '{color}' supplied for cava widget")
        self._bars = max(1, int(self.config.get("bars", 10)))

        self._cava_label = Label(
            v_align="center",
            h_align="center",
            style=f"color: {color};",
        )
        self.container_box.children = Box(spacing=1, children=[self._cava_label])

        self._owner = f"cava-widget-{id(self)}"
        self._service = cava_service
        self._frame_handler_id = self._service.connect("frame", self._on_frame)

        self.connect(
            "clicked",
            lambda _: exec_shell_command_async(
                "kitty --title cava-visualizer sh -c 'cava'", lambda *_: None
            ),
        )
        self.connect("destroy", self._on_destroy)
        self._service.set_wanted(self._owner, True, self.config)

    def _on_frame(self, *_):
        self._cava_label.set_label(bars_to_glyphs(self._service.bars[: self._bars]))

    def _on_destroy(self, *_):
        self._service.set_wanted(self._owner, False)
        safe_disconnect(self._service, self._frame_handler_id)
        self._frame_handler_id = None

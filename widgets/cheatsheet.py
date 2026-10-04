"""Bar button that toggles the keymap cheatsheet overlay."""

from modules.cheatsheet import toggle_cheatsheet
from shared.widget_container import ButtonWidget
from utils.i18n import _
from utils.widget_utils import nerd_font_icon


class CheatSheetWidget(ButtonWidget):
    """Panel widget that opens the keymap cheatsheet window."""

    def __init__(self, **kwargs):
        super().__init__(name="cheatsheet", **kwargs)

        self.add_panel_content(
            nerd_font_icon(
                icon=self.config.get("icon", "󰌌"),
                props={"style_classes": ["panel-font-icon"]},
            )
            if self.format_shows_icon()
            else None,
        )

        self.set_tooltip_if_enabled(_("widget.cheatsheet.tooltip"), default=True)

        self.connect("clicked", lambda *_: toggle_cheatsheet())

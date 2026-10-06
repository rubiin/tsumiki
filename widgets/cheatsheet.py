"""Bar button that toggles the keymap cheatsheet overlay."""

from modules.cheatsheet import toggle_cheatsheet
from shared.widget_container import ButtonWidget
from utils.i18n import _


class CheatSheetWidget(ButtonWidget):
    """Panel widget that opens the keymap cheatsheet window."""

    def __init__(self, **kwargs):
        super().__init__(name="cheatsheet", **kwargs)

        self.label_format = self.config.get("label_format", "󰌌")
        self.add_formatted_label(self.label_format)

        self.set_tooltip_if_enabled(_("widget.cheatsheet.tooltip"), default=True)

        self.connect("clicked", lambda *_: toggle_cheatsheet())

from modules.wallpaper import WallPaperPickerOverlay
from shared.widget_container import ButtonWidget
from utils.i18n import _
from utils.widget_utils import nerd_font_icon


class WallpaperWidget(ButtonWidget):
    """A widget to show the wallpaper picker."""

    def __init__(self, **kwargs):
        super().__init__(name="wallpaper", **kwargs)

        cfg = self.config

        # Optional tooltip
        self.set_tooltip_if_enabled(_("widget.wallpaper.tooltip"))

        self.add_panel_content(
            nerd_font_icon(
                icon=cfg.get("icon"),
                props={"style_classes": ["panel-font-icon"]},
            )
            if self.format_shows_icon()
            else None,
            _("widget.wallpaper.label"),
        )

        # Lazy-init wallpaper popup
        self._wallpaper_popup = None
        self.connect("clicked", self.on_click)

    def on_click(self, *_):
        if self._wallpaper_popup is None:
            self._wallpaper_popup = WallPaperPickerOverlay()
        self._wallpaper_popup.toggle_popup()

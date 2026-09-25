
from modules.wallpaper import WallPaperPickerOverlay
from shared.widget_container import ButtonWidget
from utils.i18n import _


class WallpaperWidget(ButtonWidget):
    """A widget to show the wallpaper picker."""

    def __init__(self, **kwargs):
        super().__init__(name="wallpaper", **kwargs)

        cfg = self.config

        # Optional tooltip
        if cfg.get("tooltip"):
            self.set_tooltip_text(_("widget.wallpaper.tooltip"))

        # Add icon
        self.add_panel_content(
            cfg.get("icon"),
            _("widget.wallpaper.label"),
            show_label=cfg.get("label", True),
        )

        # Lazy-init wallpaper popup
        self._wallpaper_popup = None
        self.connect("clicked", self.on_click)

    def on_click(self, *_):
        if self._wallpaper_popup is None:
            self._wallpaper_popup = WallPaperPickerOverlay()
        self._wallpaper_popup.toggle_popup()

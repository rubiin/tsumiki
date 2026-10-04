from modules.wallpaper import WallPaperPickerOverlay
from shared.widget_container import ButtonWidget
from utils.i18n import _


class WallpaperWidget(ButtonWidget):
    """A widget to show the wallpaper picker."""

    def __init__(self, **kwargs):
        super().__init__(name="wallpaper", **kwargs)

        cfg = self.config

        # Optional tooltip
        self.set_tooltip_if_enabled(_("widget.wallpaper.tooltip"))

        self.label_format = cfg.get("label_format", "{icon} wallpaper")
        self.add_formatted_label(self.label_format, cfg.get("icon", ""))

        # Lazy-init wallpaper popup
        self._wallpaper_popup = None
        self.connect("clicked", self.on_click)

    def on_click(self, *_):
        if self._wallpaper_popup is None:
            self._wallpaper_popup = WallPaperPickerOverlay()
        self._wallpaper_popup.toggle_popup()

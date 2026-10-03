from fabric.hyprland.widgets import HyprlandLanguage
from fabric.utils import FormattedString, truncate
from fabric.widgets.label import Label

from shared.widget_container import ButtonWidget
from utils.widget_utils import nerd_font_icon


class LanguageWidget(ButtonWidget):
    """A widget to display the current language."""

    def __init__(self, **kwargs):
        super().__init__(name="language", **kwargs)

        language_widget = HyprlandLanguage

        if language_widget is None:
            self.lang = Label(
                label=self.config.get("fallback_label", "N/A"),
                style_classes="panel-text",
            )
        else:
            self.lang = language_widget(
                formatter=FormattedString(
                    "{truncate(language,length,suffix)}",
                    truncate=truncate,
                    length=self.config.get("truncation_size", 10),
                    suffix="",
                ),
                style_classes="panel-text",
            )

        if self.format_shows_icon():
            self.icon = nerd_font_icon(
                icon=self.config.get("icon"),
                props={
                    "style_classes": ["panel-font-icon"],
                },
            )
            self.container_box.add(self.icon)

        self.container_box.add(self.lang)

        self.set_tooltip_if_enabled(f"Language: {self.lang.get_label()}")

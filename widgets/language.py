from fabric.hyprland.widgets import HyprlandLanguage
from fabric.utils import FormattedString, truncate
from fabric.widgets.label import Label

from shared.widget_container import ButtonWidget


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

        self.label_format = self.config.get("label_format", "{language}")
        # HyprlandLanguage stays off the panel: it is the data source, and its
        # text is folded into the single formatted label.
        self.add_formatted_label(self.label_format, language=self.lang.get_label())
        self._register_handlers(self.lang, {"layout_changed": self._refresh_language})

        self.set_tooltip_if_enabled(f"Language: {self.lang.get_label()}")

    def _refresh_language(self, *_args) -> None:
        """Mirror the live language widget into the panel label and tooltip."""
        language = self.lang.get_label()
        self.refresh_formatted_label(language=language)
        self.set_tooltip_if_enabled(f"Language: {language}")

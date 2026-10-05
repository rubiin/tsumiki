from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label

from services.quotes import QuotesService
from shared.widget_container import BaseWindow
from utils.functions import convert_seconds_to_milliseconds
from utils.i18n import _
from utils.widget_settings import BarConfig


class DesktopQuote(BaseWindow):
    """
    A simple desktop quote widget.
    """

    def __init__(self, config: BarConfig, **kwargs):
        self.config = config.get("modules", {}).get("desktop_quotes", {})

        self.quote_label = Label(
            name="desktop_quotes-quote-label",
            label=_("common.loading"),
            line_wrap="word-char",
            chars_width=50,
            h_expand=True,
        )

        self.author_label = Label(
            name="desktop_quotes-author-label",
            label=_("common.loading"),
            line_wrap="word-char",
            chars_width=40,
            h_align="end",
            justification="right",
            h_expand=True,
        )

        super().__init__(
            name="desktop_quotes",
            layer=self.config.get("layer", "top"),
            anchor=self.config.get("anchor", "center"),
            child=Box(
                name="desktop_quotes-box",
                orientation="v",
                children=(self.quote_label, self.author_label),
            ),
            **kwargs,
        )

        self.quote_service = QuotesService()
        self.update_quote()

        self._register_repeater(
            invoke_repeater(
                convert_seconds_to_milliseconds(
                    self.config.get("interval", 600)
                ),
                self.update_quote,
            )
        )

    def update_quote(self):
        """Kick off an async quote fetch; the UI updates via the callback."""
        self.quote_service.get_quotes_async(self._on_quote_ready)
        return True  # Keep the repeater running

    def _on_quote_ready(self, quote):
        """Apply the fetched quote (runs on the main thread via idle_add)."""
        if quote:
            self.quote_label.set_label(quote["q"])
            self.author_label.set_label("- " + quote["a"])
        else:
            self.quote_label.set_text(_("common.error"))

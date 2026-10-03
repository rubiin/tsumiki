from fabric.widgets.label import Label

from services import audio_service
from shared.widget_container import ButtonWidget
from utils.icons import get_text_icon
from utils.widget_utils import nerd_font_icon


# TODO: review this widget
class MicrophoneIndicatorWidget(ButtonWidget):
    """A widget to display the current microphone status."""

    def __init__(self, **kwargs):
        super().__init__(name="microphone", **kwargs)

        self.mic_on_icon = get_text_icon("microphone.high", "")
        self.mic_off_icon = get_text_icon("microphone.muted", "")

        self.icon = None

        # Initialize the audio service
        self.audio_service = audio_service

        if self.format_shows_icon():
            self.icon = nerd_font_icon(
                icon=self.mic_off_icon,
                props={"style_classes": ["panel-font-icon"]},
            )
            self.container_box.add(self.icon)

        if self.config.get("label", True):
            self.mic_label = Label(
                label="mic",
                style_classes="panel-text",
            )
            self.container_box.add(self.mic_label)

        self._register_handlers(
            self.audio_service,
            {"microphone_changed": self._update_status},
        )
        self._update_status()

    def _update_status(self, *_):
        current_microphone = self.audio_service.microphone

        if not current_microphone:
            if self.icon is not None:
                self.icon.set_visible(False)
            return True

        is_muted = current_microphone.muted

        if self.icon is not None:
            self.icon.set_label(self.mic_off_icon if is_muted else self.mic_on_icon)
            self.icon.set_visible(True)

        # Update the label if enabled
        if self.config.get("label", True):
            self.mic_label.set_label("Off" if is_muted else "On")

        self.set_tooltip_if_enabled(
            "Microphone is muted" if is_muted else "Microphone is on"
        )

        return True

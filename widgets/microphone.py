
from services import audio_service
from shared.widget_container import ButtonWidget
from utils.icons import get_text_icon


# TODO: review this widget
class MicrophoneIndicatorWidget(ButtonWidget):
    """A widget to display the current microphone status."""

    def __init__(self, **kwargs):
        super().__init__(name="microphone", **kwargs)

        self.mic_on_icon = get_text_icon("microphone.high", "")
        self.mic_off_icon = get_text_icon("microphone.muted", "")

        # Initialize the audio service
        self.audio_service = audio_service

        self.label_format = self.config.get("label_format", "{icon}")
        self.add_formatted_label(self.label_format, self.mic_off_icon)

        self._register_handlers(
            self.audio_service,
            {"microphone_changed": self._update_status},
        )
        self._update_status()

    def _update_status(self, *_):
        current_microphone = self.audio_service.microphone

        if not current_microphone:
            self.panel_label.set_visible(False)
            return True

        self.panel_label.set_visible(True)
        is_muted = current_microphone.muted

        self.refresh_formatted_label(
            self.mic_off_icon if is_muted else self.mic_on_icon
        )

        self.set_tooltip_if_enabled(
            "Microphone is muted" if is_muted else "Microphone is on"
        )

        return True

from time import monotonic

from fabric.utils import GLib

from services import audio_service
from shared.widget_container import ButtonWidget
from utils.icons import get_text_icon

_FADE_FRAME_MS = 16
_FADE_MS = 150


# TODO: review this widget
class MicrophoneIndicatorWidget(ButtonWidget):
    """A widget to display the current microphone status."""

    def __init__(self, **kwargs):
        super().__init__(name="microphone", **kwargs)

        self._resolve_icons()

        # Initialize the audio service
        self.audio_service = audio_service

        self.label_format = self.config.get("label_format", "")
        self.add_formatted_label(self.label_format, self.mic_off_icon, state="muted")

        self._register_handlers(
            self.audio_service,
            {"microphone_changed": self._update_status},
        )
        self._update_status()

    def _resolve_icons(self):
        """Resolve the on/off glyphs, preferring configured overrides."""
        self.mic_on_icon = self.config.get("icon_active") or get_text_icon(
            "microphone.high", ""
        )
        self.mic_off_icon = self.config.get("icon_muted") or get_text_icon(
            "microphone.muted", ""
        )

    def _update_status(self, *_):
        current_microphone = self.audio_service.microphone

        if not current_microphone:
            self.panel_label.set_visible(False)
            return True

        was_visible = self.panel_label.get_visible()
        self.panel_label.set_visible(True)
        if not was_visible:
            self.panel_label.set_opacity(0.0)
            self._start_panel_label_fade()
        is_muted = current_microphone.muted

        self.refresh_formatted_label(
            self.mic_off_icon if is_muted else self.mic_on_icon,
            state="muted" if is_muted else "on",
        )

        self.set_tooltip_if_enabled(
            "Microphone is muted" if is_muted else "Microphone is on"
        )

        return True

    def _start_panel_label_fade(self):
        started = monotonic()

        def step() -> bool:
            progress = min(1.0, (monotonic() - started) * 1000 / _FADE_MS)
            self.panel_label.set_opacity(progress)
            return progress < 1.0

        GLib.timeout_add(_FADE_FRAME_MS, step)

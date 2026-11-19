from fabric.utils import cooldown

from services import audio_service
from shared.scrollable_progress import ScrollableProgressWidget
from utils.functions import safe_disconnect
from utils.icons import get_text_icon
from utils.widget_utils import get_audio_icon_name


class VolumeWidget(ScrollableProgressWidget):
    """A widget that displays and controls the volume."""

    def __init__(self, **kwargs):
        super().__init__(
            name="volume",
            icon_name="volume.medium",
            icon_style_classes=["panel-font-icon", "overlay-icon"],
            events=["scroll", "smooth-scroll", "enter-notify-event"],
            initial_progress=(
                audio_service.speaker.volume / 100 if audio_service.speaker else 0.0
            ),
            **kwargs,
        )
        self._speaker = None
        self._speaker_volume_handler_id = None

        self.level_icons = self.config.get("level_icons") or []
        self.icon_muted = self.config.get("icon_muted") or get_text_icon(
            "volume.muted", "󰝟"
        )

        # Initialize the audio service
        self.audio = audio_service

        # Connect the audio service to update the progress bar on volume change
        self._register_handlers(
            self.audio,
            {"notify::speaker": self.on_speaker_changed},
        )

        # Connect the event box to handle scroll events
        self.connect("scroll-event", self.on_scroll)

        # GTK destroys panel widgets from C, so cleanup hangs off the signal.
        self.connect("destroy", self._on_destroy)

    @cooldown(0.1)
    def on_scroll(self, _, event):
        # Adjust the volume based on the scroll direction
        if not self.audio.speaker:
            return

        val_y = event.delta_y
        step_size = self.config.get("step_size", 5)

        if val_y > 0:
            self.audio.speaker.volume += step_size
        else:
            self.audio.speaker.volume -= step_size

    def on_speaker_changed(self, *_):
        # Update the progress bar value based on the speaker volume
        speaker = self.audio.speaker
        if not speaker:
            return

        if self._speaker and self._speaker_volume_handler_id is not None:
            safe_disconnect(self._speaker, self._speaker_volume_handler_id)
            self._speaker_volume_handler_id = None

        self.set_tooltip_if_enabled(speaker.description)

        self._speaker = speaker
        self._speaker_volume_handler_id = speaker.connect(
            "notify::volume", self.update_volume
        )
        self.update_volume()

    # Mute and unmute the speaker
    def toggle_mute(self):
        current_stream = self.audio.speaker
        if current_stream:
            current_stream.muted = not current_stream.muted
            self.icon.set_text(
                self.icon_muted
            ) if current_stream.muted else self.update_volume()

    def _icon_for_volume(self, volume: int, muted: bool) -> str:
        return get_audio_icon_name(
            volume, muted, self.level_icons, self.icon_muted
        )["icon_text"]

    def update_volume(self, *_):
        speaker = self.audio.speaker
        if not speaker:
            return

        volume = round(speaker.volume)
        icon_text = self._icon_for_volume(volume, speaker.muted)
        self.update_progress(volume / 100, icon_text)

    def _on_destroy(self, *_):
        """Detach from the speaker; runs even when the parent destroys us from C."""
        if self._speaker and self._speaker_volume_handler_id is not None:
            safe_disconnect(self._speaker, self._speaker_volume_handler_id)
        self._speaker_volume_handler_id = None
        self._speaker = None

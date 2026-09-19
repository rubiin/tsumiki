from fabric.utils import cooldown

from services import audio_service
from shared.buttons import HoverButton
from shared.setting_scale import SettingSlider
from utils.icons import get_text_icon
from utils.widget_utils import get_audio_icon_name, nerd_font_icon


class AudioSlider(SettingSlider):
    """A scale for audio settings (device or per-application streams)."""

    def init_device_audio(self, *_):
        if not self.client.speaker:
            return
        self.audio_stream = self.client.speaker
        self.update_state()
        self.client.disconnect_by_func(self.init_device_audio)
        self.client.connect("speaker-changed", self.update_state)

    def __init__(self, audio_stream=None, show_chevron=False):
        """Initialize the audio slider."""
        self.client = audio_service
        self.audio_stream = audio_stream

        # Initialize with default values first
        super().__init__(
            icon_name=get_text_icon("volume.high", "󰕾"),
            start_value=0,
            pixel_size=20,
        )

        if show_chevron:
            self.chevron_icon = nerd_font_icon(
                icon=get_text_icon("chevron.right", ""),
                props={"style_classes": ["chevron-icon"]},
            )

            self.chevron_btn = HoverButton(
                style_classes="audio-chevron-button",
                child=self.chevron_icon,
                on_clicked=self.on_button_click,
            )
            self.children = (*self.children, self.chevron_btn)

        self._stream_handler = None
        self._destroyed = False
        if not audio_stream:
            self.client.connect("changed", self.init_device_audio)
            if self.client.speaker:
                self.init_device_audio()
        else:
            self.update_state()
            self._stream_handler = self.audio_stream.connect(
                "changed", self.update_state
            )

        # Connect signals
        self.scale.connect("change-value", self.on_scale_move)

        self.icon_button.connect("clicked", self.on_mute_click)

        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, *_):
        # Disconnect the stream handler — streams outlive the destroyed slider.
        self._destroyed = True
        if self._stream_handler is not None and self.audio_stream is not None:
            self.audio_stream.disconnect(self._stream_handler)
            self._stream_handler = None

    def update_state(self, *_):
        """Update the slider state from the audio stream."""
        if not self.audio_stream or self._destroyed:
            return

        volume = int(self.audio_stream.volume)
        is_muted = self.audio_stream.muted

        self.scale.set_sensitive(not is_muted)
        self.toggle_css_class("muted", is_muted)

        # Avoid unnecessary updates if the value hasn't changed
        if volume == round(self.scale.get_value()):
            return

        is_over_amplified = volume > 100
        self.toggle_css_class("overamplified", is_over_amplified)

        self.scale.set_value(volume)
        self.scale.set_tooltip_text(f"{volume}%")
        self.update_icon(volume)

    def update_icon(self, volume=0):
        if not self.audio_stream:
            return
        icon_name = get_audio_icon_name(volume, self.audio_stream.muted)["icon_text"]

        self.icon.set_label(icon_name)

    @cooldown(0.1)
    def on_scale_move(self, _, __, moved_pos: float):
        """Handle volume slider changes."""
        if self.audio_stream:
            self.audio_stream.volume = moved_pos

    def on_button_click(self, *_):
        parent = self.get_parent()
        while parent and not hasattr(parent, "audio_submenu"):
            parent = parent.get_parent()

        if parent and hasattr(parent, "audio_submenu"):
            is_visible = parent.audio_submenu.toggle_reveal()

            self.chevron_icon.set_label(
                get_text_icon("chevron.down", "")
                if is_visible
                else get_text_icon("chevron.right", "")
            )

    def on_mute_click(self, *_):
        """Toggle mute state."""
        if self.audio_stream:
            self.audio_stream.muted = not self.audio_stream.muted

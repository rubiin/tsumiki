from fabric.utils import cooldown
from fabric.widgets.box import Box

from services import audio_service
from shared.buttons import HoverButton
from shared.setting_scale import SettingSlider
from utils.icons import get_text_icon
from utils.widget_utils import nerd_font_icon


class MicrophoneSlider(SettingSlider):
    """A widget to display a scale for audio settings."""

    def __init__(self, audio_stream=None, show_chevron=True):
        self.client = audio_service
        self.audio_stream = audio_stream

        self.pixel_size = 16

        super().__init__(
            icon_name=get_text_icon("microphone.medium", "󰖂"),
            start_value=0,
            pixel_size=self.pixel_size,
        )

        if show_chevron:
            self.chevron_icon = nerd_font_icon(
                icon=get_text_icon("chevron.right", ""),
                props={"style_classes": ["chevron-icon"]},
            )
            self.chevron_btn = HoverButton(
                child=Box(
                    children=(self.chevron_icon,),
                ),
                on_clicked=self.on_click,
            )
            self.children = (*self.children, self.chevron_btn)

        if not audio_stream:

            def init_device_audio(*_):
                if not self.client.microphone:
                    return
                self.audio_stream = self.client.microphone
                self.update_state()
                self.client.disconnect_by_func(init_device_audio)
                self.client.connect("microphone-changed", self.update_state)

            self.client.connect("changed", init_device_audio)
            if self.client.microphone:
                init_device_audio()
        else:
            self.update_state()
            self.audio_stream.connect("changed", self.update_state)

        self.scale.connect("change-value", self.on_scale_move)
        self.icon_button.connect("clicked", self.on_mute_click)
        self._destroyed = False
        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, *_):
        self._destroyed = True

    @cooldown(1)
    def on_scale_move(self, _, __, moved_pos: float):
        self.client.microphone.volume = moved_pos

    def update_state(self, *_):
        """Update the slider state from the audio stream."""
        if not self.audio_stream or self._destroyed:
            return

        volume = round(self.audio_stream.volume)
        is_muted = self.audio_stream.muted

        # Update mute-dependent UI even when the volume is unchanged.
        self.scale.set_sensitive(not is_muted)
        self.toggle_css_class("muted", is_muted)

        # Avoid unnecessary updates if the value hasn't changed
        if volume == round(self.scale.get_value()):
            return

        self.scale.set_value(volume)
        self.scale.set_tooltip_text(f"{volume}%")
        self.icon.set_label(self._get_icon_name())

    def _get_icon_name(self):
        """Get the appropriate icon name based on mute state."""
        if not self.audio_stream:
            return get_text_icon("microphone.high", "")
        return get_text_icon(
            f"microphone.{'muted' if self.audio_stream.muted else 'high'}"
        )

    def on_click(self, *_):
        parent = self.get_parent()
        while parent and not hasattr(parent, "mic_submenu"):
            parent = parent.get_parent()

        if parent and hasattr(parent, "mic_submenu"):
            is_visible = parent.mic_submenu.toggle_reveal()

            self.chevron_icon.set_label(
                get_text_icon("chevron.down", "")
                if is_visible
                else get_text_icon("chevron.right", "")
            )

    def on_mute_click(self, *_):
        if self.audio_stream:
            self.client.microphone.muted = not self.client.microphone.muted

from typing import Literal

from fabric.utils import idle_add
from fabric.widgets.box import Box
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer

from shared.widget_container import BaseWidget, BaseWindow
from utils.icons import symbolic_icons
from utils.types import Keyboard_Mode
from utils.widget_settings import BarConfig
from utils.widget_utils import (
    create_scale,
)


class GenericOSDContainer(Box, BaseWidget):
    """A generic OSD container to display the OSD for brightness and audio."""

    def __init__(self, config: dict, **kwargs):
        is_vertical = config.get("orientation", "horizontal") == "vertical"

        super().__init__(
            orientation=config.get("orientation", "horizontal"),
            spacing=10,
            name="osd-container",
            style_classes="vertical" if is_vertical else [],
            **kwargs,
        )

        self.icon_size = config.get("icon_size", 28)

        self.icon = Image(
            icon_name=symbolic_icons["brightness"]["screen"],
            icon_size=self.icon_size,
        )

        scale_style = (
            "scale {min-height: 150px; min-width: 11px;}" if is_vertical else ""
        )

        self.scale = create_scale(
            name="osd-scale",
            orientation=config.get("orientation", "horizontal"),
            h_expand=is_vertical,
            v_expand=is_vertical,
            duration=0.8,
            curve=(0.34, 1.56, 0.64, 1.0),
            inverted=is_vertical,
            style=scale_style,
        )

        self.children = (self.icon, self.scale)

        self.show_level = config.get("percentage", True)

        if self.show_level:
            self.level = Label(name="osd-level", h_align="center", h_expand=True)
            self.add(self.level)

    def update_values(self, value):
        """Update the value."""
        round_value = round(value)
        self.scale.set_value(round_value)

        if self.show_level:
            self.level.set_label(f"{round_value}%")


class OSDContainer(BaseWindow):
    """A widget to display the OSD for audio and brightness."""

    _HIDE_TIMER = "hide"
    _FINALIZE_TIMER = "finalize-hide"

    def __init__(
        self,
        config: BarConfig,
        keyboard_mode: Keyboard_Mode = "none",
        **kwargs,
    ):
        self.config = config.get("modules", {}).get("osd", {})

        osds = self.config.get("osds", ["brightness", "volume"])

        if "volume" in osds:
            from .osds.audio import AudioOSDContainer

            self.audio_container = AudioOSDContainer(config=self.config)
            self.audio_container.connect("volume-changed", self.show_audio)
        if "brightness" in osds:
            from .osds.brightness import BrightnessOSDContainer

            self.brightness_container = BrightnessOSDContainer(config=self.config)
            self.brightness_container.connect(
                "brightness-changed", self.show_brightness
            )
        if "microphone" in osds:
            from .osds.microphone import MicrophoneOSDContainer

            self.microphone_container = MicrophoneOSDContainer(config=self.config)
            self.microphone_container.connect("mic-changed", self.show_microphone)
        if "lockkeys" in osds:
            from .osds.lockkeys import LockkeysOSDContainer

            self.lockkeys_container = LockkeysOSDContainer(config=self.config)
            self.lockkeys_container.connect("locks-changed", self.show_lockkeys)

        self.timeout = self.config.get("timeout", 3000)

        self.revealer = Revealer(
            name="osd-revealer",
            transition_type=self.config.get("transition_type", "slide-up"),
            transition_duration=self.config.get("transition_duration", 500),
            child_revealed=False,
        )

        super().__init__(
            layer="overlay",
            anchor=self.config.get("anchor", "center"),
            child=self.revealer,
            visible=False,
            pass_through=True,
            keyboard_mode=keyboard_mode,
            name="osd",
            title="tsumiki",
            **kwargs,
        )

    def show_audio(self, *_):
        self.show_box(box_to_show="audio")

    def show_brightness(self, *_):
        self.show_box(box_to_show="brightness")

    def show_microphone(self, *_):
        self.show_box(box_to_show="microphone")

    def show_lockkeys(self, *_):
        self.show_box(box_to_show="lockkeys")

    def show_box(
        self, box_to_show: Literal["audio", "brightness", "microphone", "lockkeys"]
    ):
        if box_to_show == "audio":
            child_to_show = self.audio_container
        elif box_to_show == "brightness":
            child_to_show = self.brightness_container
        elif box_to_show == "microphone":
            child_to_show = self.microphone_container
        else:
            child_to_show = self.lockkeys_container

        if self.revealer.get_child() != child_to_show:
            if self.revealer.get_child():
                self.revealer.remove(self.revealer.get_child())
            self.revealer.add(child_to_show)

        # First make the window visible
        self.set_visible(True)

        # Reset hide timer and pending finalize
        self._cancel_timeout(self._HIDE_TIMER)
        self._cancel_timeout(self._FINALIZE_TIMER)

        # Delay reveal to ensure animation plays
        idle_add(lambda: self.revealer.set_reveal_child(True))

        self._schedule_timeout(self._HIDE_TIMER, self.timeout, self._hide)

    def _hide(self):
        self.revealer.set_reveal_child(False)  # Trigger hide animation

        # Wait for the animation to finish before hiding the window completely
        duration = self.revealer.get_transition_duration()
        self._schedule_timeout(self._FINALIZE_TIMER, duration, self._finalize_hide)
        return False

    def _finalize_hide(self):
        self.set_visible(False)
        return False

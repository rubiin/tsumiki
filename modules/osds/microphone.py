from typing import ClassVar

from fabric.utils import GObject

from utils.icons import symbolic_icons

from .audio_device import AudioDeviceOSDContainer


class MicrophoneOSDContainer(AudioDeviceOSDContainer):
    """A widget to display the OSD for microphone."""

    __gsignals__: ClassVar = {"mic-changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    device_attribute: ClassVar[str] = "microphone"
    changed_signal: ClassVar[str] = "mic-changed"
    # Unlike the speaker, a new capture device starts from a clean slate so the
    # first reading is always published.
    reset_state_on_device_change: ClassVar[bool] = True

    def _icon_for(self, volume: int, muted: bool) -> str:
        return (
            symbolic_icons["audio"]["mic"]["muted"]
            if volume == 0 or muted
            else symbolic_icons["audio"]["mic"]["high"]
        )

from typing import ClassVar

from fabric.utils import GObject

from utils.widget_utils import (
    get_audio_icon_name,
)

from .audio_device import AudioDeviceOSDContainer


class AudioOSDContainer(AudioDeviceOSDContainer):
    """A widget to display the OSD for audio."""

    __gsignals__: ClassVar = {
        "volume-changed": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    device_attribute: ClassVar[str] = "speaker"
    changed_signal: ClassVar[str] = "volume-changed"
    # PipeWire re-announces the sink unchanged; resetting pops the OSD needlessly.
    reset_state_on_device_change: ClassVar[bool] = False

    def _icon_for(self, volume: int, muted: bool) -> str:
        return get_audio_icon_name(volume, muted)["icon"]

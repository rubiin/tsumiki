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
    # Keep previous_volume/previous_muted across a device re-announcement:
    # PipeWire re-announces the default sink on profile/port changes and sink
    # suspend/resume with an identical volume, and resetting the state here made
    # update_volume() treat that as a change and pop the OSD with no actual
    # value change.
    reset_state_on_device_change: ClassVar[bool] = False

    def _icon_for(self, volume: int, muted: bool) -> str:
        return get_audio_icon_name(volume, muted)["icon"]

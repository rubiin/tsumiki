"""Shared behaviour for the volume OSD of an audio device.

The speaker and microphone OSDs are the same widget watching a different
device, so the device attribute, the container's own signal name and the icon
set are the only things that differ.
"""

from typing import ClassVar

from fabric.utils import bulk_connect, cooldown

from services import audio_service

from ..osd import GenericOSDContainer


class AudioDeviceOSDContainer(GenericOSDContainer):
    """Watches one audio device and reflects its level and mute state.

    Subclasses set :attr:`device_attribute`, :attr:`changed_signal` and
    :attr:`reset_state_on_device_change`, and implement :meth:`_icon_for`.
    """

    #: Attribute on the audio service holding the device to watch.
    device_attribute: ClassVar[str] = ""
    #: Signal this container emits when the level or mute state changes.
    changed_signal: ClassVar[str] = ""
    #: Whether a device re-announcement clears the tracked previous state.
    reset_state_on_device_change: ClassVar[bool] = False

    def _icon_for(self, volume: int, muted: bool) -> str:
        """Return the icon name for a level and mute state."""
        raise NotImplementedError

    def __init__(self, config: dict, **kwargs):
        super().__init__(
            config=config,
            **kwargs,
        )
        self.audio_service = audio_service
        self._device = None
        self._device_handler_id: int | None = None

        self.previous_volume = None
        self.previous_muted = None
        self._effective_muted = None

        self.config = config

        bulk_connect(
            self.audio_service,
            {
                f"notify::{self.device_attribute}": self.on_device_changed,
                "changed": self.check_mute,
            },
        )
        self.on_device_changed()

    def _current_device(self):
        return getattr(self.audio_service, self.device_attribute)

    @cooldown(0.1)
    def check_mute(self, *_):
        device = self._current_device()
        if not device:
            return

        current_muted = device.muted
        if self.previous_muted is None or current_muted != self.previous_muted:
            self.previous_muted = current_muted
            self.update_icon()
            self.scale.toggle_css_class("muted", current_muted)
            self.emit(self.changed_signal)

    def on_device_changed(self, *_):
        """Re-wire the volume handler onto whichever device is now current."""
        if self._device and self._device_handler_id is not None:
            self._device.disconnect(self._device_handler_id)
        self._device_handler_id = None

        if self.reset_state_on_device_change:
            self.previous_volume = None
            self.previous_muted = None
            self._effective_muted = None

        self._device = self._current_device()

        if self._device:
            self._device_handler_id = self._device.connect(
                "notify::volume", self.update_volume
            )
            self.update_volume(self._device)

    @cooldown(0.1)
    def update_volume(self, *_):
        device = self._current_device()
        if not device:
            return

        volume = round(device.volume)
        current_muted = device.muted
        volume_changed = self.previous_volume is None or volume != self.previous_volume
        muted_changed = (
            self.previous_muted is None or current_muted != self.previous_muted
        )

        if volume_changed or muted_changed:
            self.previous_volume = volume
            self.previous_muted = current_muted

            is_muted = device.muted or volume == 0

            self.scale.toggle_css_class("overamplified", volume > 100)

            if self._effective_muted is None or is_muted != self._effective_muted:
                self._effective_muted = is_muted
                self.scale.toggle_css_class("muted", is_muted)

            if is_muted:
                self.update_icon()
            else:
                self.update_icon(volume)

            self.update_values(volume)
            self.emit(self.changed_signal)

    def update_icon(self, volume=0):
        icon_name = self._icon_for(volume, self._current_device().muted)
        self.icon.set_from_icon_name(icon_name, self.icon_size)

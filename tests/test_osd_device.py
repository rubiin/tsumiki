"""Tests for the shared audio-device OSD container.

The speaker and microphone OSDs are the same widget, and the one behaviour that
must not be unified is what happens to the tracked state when the device is
re-announced. Built via ``__new__`` and stubs: real widgets need a display.
"""

import unittest
from unittest import mock

from modules.osds.audio import AudioOSDContainer
from modules.osds.audio_device import AudioDeviceOSDContainer
from modules.osds.microphone import MicrophoneOSDContainer


def make_container(cls):
    container = cls.__new__(cls)
    container.audio_service = mock.Mock()
    container._device = None
    container._device_handler_id = None
    container.previous_volume = None
    container.previous_muted = None
    container._effective_muted = None
    container.icon = mock.Mock()
    container.icon_size = 24
    container.scale = mock.Mock()
    container.emit = mock.Mock()
    container.update_values = mock.Mock()
    # Isolate on_device_changed from the cooldown-wrapped update_volume.
    container.update_volume = mock.Mock()
    return container


def make_device(volume: float = 40.0, muted: bool = False):
    device = mock.Mock()
    device.volume = volume
    device.muted = muted
    device.connect.return_value = 7
    return device


class DevicePolicyTest(unittest.TestCase):
    """Each container declares its own device, signal and reset policy."""

    def test_speaker_watches_the_speaker(self):
        self.assertEqual("speaker", AudioOSDContainer.device_attribute)
        self.assertEqual("volume-changed", AudioOSDContainer.changed_signal)

    def test_microphone_watches_the_microphone(self):
        self.assertEqual("microphone", MicrophoneOSDContainer.device_attribute)
        self.assertEqual("mic-changed", MicrophoneOSDContainer.changed_signal)

    def test_only_the_microphone_resets_on_a_device_change(self):
        """The divergence: the speaker keeps its state, on purpose."""
        self.assertFalse(AudioOSDContainer.reset_state_on_device_change)
        self.assertTrue(MicrophoneOSDContainer.reset_state_on_device_change)

    def test_both_derive_from_the_shared_base(self):
        self.assertTrue(issubclass(AudioOSDContainer, AudioDeviceOSDContainer))
        self.assertTrue(issubclass(MicrophoneOSDContainer, AudioDeviceOSDContainer))


class OnDeviceChangedTest(unittest.TestCase):
    """Rewiring onto a new device, without losing the old handler."""

    def test_connects_the_new_device_and_updates(self):
        container = make_container(AudioOSDContainer)
        device = make_device()
        container.audio_service.speaker = device

        container.on_device_changed()

        device.connect.assert_called_once_with(
            "notify::volume", container.update_volume
        )
        container.update_volume.assert_called_once_with(device)

    def test_disconnects_the_previous_device_first(self):
        container = make_container(AudioOSDContainer)
        old = make_device()
        container._device = old
        container._device_handler_id = 7

        container.on_device_changed()

        old.disconnect.assert_called_once_with(7)

    def test_speaker_keeps_its_tracked_state(self):
        container = make_container(AudioOSDContainer)
        container.previous_volume = 40
        container.previous_muted = True
        container._effective_muted = True
        container.audio_service.speaker = make_device(volume=40, muted=True)

        container.on_device_changed()

        self.assertEqual(40, container.previous_volume)
        self.assertTrue(container.previous_muted)
        self.assertTrue(container._effective_muted)

    def test_microphone_clears_its_tracked_state(self):
        container = make_container(MicrophoneOSDContainer)
        container.previous_volume = 40
        container.previous_muted = True
        container._effective_muted = True
        container.audio_service.microphone = make_device(volume=40, muted=True)

        container.on_device_changed()

        self.assertIsNone(container.previous_volume)
        self.assertIsNone(container.previous_muted)
        self.assertIsNone(container._effective_muted)

    def test_no_device_means_no_handler(self):
        container = make_container(AudioOSDContainer)
        container.audio_service.speaker = None

        container.on_device_changed()

        self.assertIsNone(container._device)
        self.assertIsNone(container._device_handler_id)
        container.update_volume.assert_not_called()


class IconSelectionTest(unittest.TestCase):
    """Each device maps a level and mute state to its own icon."""

    def test_speaker_uses_the_shared_volume_icons(self):
        container = make_container(AudioOSDContainer)
        device = make_device(muted=False)
        container.audio_service.speaker = device

        with mock.patch(
            "modules.osds.audio.get_audio_icon_name", return_value={"icon": "vol-40"}
        ) as get_icon:
            container.update_icon(40)

        get_icon.assert_called_once_with(40, False)
        container.icon.set_from_icon_name.assert_called_once_with("vol-40", 24)

    def test_microphone_picks_high_or_muted(self):
        container = make_container(MicrophoneOSDContainer)
        device = make_device(volume=40, muted=False)
        container.audio_service.microphone = device

        container.update_icon(40)
        from utils.icons import symbolic_icons

        container.icon.set_from_icon_name.assert_called_once_with(
            symbolic_icons["audio"]["mic"]["high"], 24
        )

    def test_microphone_muted_icon_when_the_device_is_muted(self):
        container = make_container(MicrophoneOSDContainer)
        container.audio_service.microphone = make_device(muted=True)

        container.update_icon(40)
        from utils.icons import symbolic_icons

        container.icon.set_from_icon_name.assert_called_once_with(
            symbolic_icons["audio"]["mic"]["muted"], 24
        )


if __name__ == "__main__":
    unittest.main()

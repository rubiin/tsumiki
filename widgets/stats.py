import json
from time import monotonic

from fabric.utils import exec_shell_command, exec_shell_command_async, idle_add, logger
from fabric.widgets.label import Label

import utils.functions as helpers
from services.networkspeed import NetworkSpeed
from shared.mixins import StatDisplayMixin
from shared.widget_container import ButtonWidget
from utils.icons import get_text_icon
from utils.widget_utils import (
    connect_util_fabricator_changed,
    disconnect_util_fabricator_changed,
)


class FabricatorBoundWidget(ButtonWidget):
    """Button widget with safe util_fabricator signal lifecycle."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._util_changed_handler_id = None
        self.connect("destroy", self._disconnect_fabricator)

    def _bind_fabricator_changed(self, callback):
        self._util_changed_handler_id = connect_util_fabricator_changed(callback)

    def _disconnect_fabricator(self, *_):
        if self._util_changed_handler_id is None:
            return

        disconnect_util_fabricator_changed(self._util_changed_handler_id)
        self._util_changed_handler_id = None


class CpuWidget(FabricatorBoundWidget, StatDisplayMixin):
    """A widget to display the current CPU usage."""

    def __init__(
        self,
        **kwargs,
    ):
        # Initialize the Box with specific name and style
        super().__init__(
            name="cpu",
            **kwargs,
        )

        exec_shell_command_async(
            "bash -c \"lscpu | grep 'Model name' | awk -F: '{print $2}'\"",
            self.set_cpu_name,
        )

        # Setup display mode using mixin
        self.setup_stat_display(self.container_box)

        # Set up a fabricator to call the update_label method when the CPU usage changes
        self._bind_fabricator_changed(self._update_ui)

    def set_cpu_name(self, cpu_name: str):
        self.cpu_name = cpu_name.strip()

    def _update_ui(self, _, value: dict):
        # Update the label with the current CPU usage if enabled
        frequency = value.get("cpu_freq")
        usage = value.get("cpu_usage")

        # Use mixin to update display
        self.update_stat_display(usage, f"{usage}%")

        # Update the tooltip with the memory usage details if enabled
        if self.config.get("tooltip", False) and self.tooltips_enabled:
            temp = value.get("temperature")

            temp = temp.get(self.config.get("sensor", ""))

            if temp is None:
                return "N/A"

            # current temperature
            temp = temp[-1][1] if temp else 0

            temp = round(temp) if self.config.get("round", True) else temp

            is_celsius = self.config.get("temperature_unit", "celsius") == "celsius"

            temp = (
                f"{temp} °C"
                if is_celsius
                else f"{helpers.celsius_to_fahrenheit(temp)} °F"
            )

            if isinstance(frequency, (list, tuple)) and frequency:
                freq_text = f"{round(frequency[0], 2)} MHz"
            else:
                freq_text = "Unknown"

            tooltip_text = (
                f"{self.cpu_name}\n"
                f"{get_text_icon('thermometer')} Temperature: {temp}\n"
                f"{get_text_icon('powerprofiles.performance')} Utilization: {usage}\n"
                f"{get_text_icon('cpu')} Clock Speed: {freq_text}"
            )

            self.set_tooltip_if_enabled(tooltip_text)

        return True


class GpuWidget(FabricatorBoundWidget, StatDisplayMixin):
    """A widget to display the current GPU usage."""

    def __init__(
        self,
        **kwargs,
    ):
        # Initialize the Box with specific name and style
        super().__init__(
            name="gpu",
            **kwargs,
        )

        # Setup display mode using mixin
        self.setup_stat_display(self.container_box)

        # Set up a fabricator to call the update_label method when the CPU usage changes
        self._bind_fabricator_changed(self._update_ui)

        # Cache for GPU stats to avoid blocking main thread
        self._gpu_stats = None
        self._gpu_request_in_flight = False
        self._last_gpu_poll = 0.0
        self._gpu_poll_interval = float(self.config.get("poll_interval", 2.5))

    def _update_ui(self, *_):
        if self._gpu_request_in_flight:
            return True

        now = monotonic()
        if (now - self._last_gpu_poll) < self._gpu_poll_interval:
            return True

        self._gpu_request_in_flight = True
        self._last_gpu_poll = now
        self._poll_gpu_stats()

        return True

    @helpers.run_in_thread
    def _poll_gpu_stats(self):
        """Poll ``nvtop -s`` off the main thread and post results back."""
        try:
            out = exec_shell_command("nvtop -s")
            data = json.loads(out)
            value = json.dumps(data[0])
        except Exception as e:
            logger.error(f"Error parsing JSON: {e}")
            value = None
        idle_add(self._finish_gpu_poll, value)

    def _finish_gpu_poll(self, value):
        """Main-thread continuation: clear the in-flight guard, then update UI."""
        self._gpu_request_in_flight = False
        if value is not None:
            self._on_gpu_stats_received(value)

    def _on_gpu_stats_received(self, value: str):
        """Handle GPU stats received from async command."""

        stats = json.loads(value)

        frequency = stats.get("gpu_clock", "0 MHz")
        usage_str = stats.get("mem_util", "0").strip("%")
        try:
            usage = float(usage_str)
        except ValueError:
            usage = 0
        gpu_name = stats.get("device_name", "N/A")

        # Use mixin to update display
        self.update_stat_display(usage, f"{usage_str}%")

        # Update the tooltip with the memory usage details if enabled
        if self.config.get("tooltip", False) and self.tooltips_enabled:
            temp = stats.get("temp")

            if temp is None:
                return "N/A"

            tooltip_text = (
                f"{gpu_name}\n"
                f" Temperature: {temp}\n"
                f"󰾆 Utilization: {usage}\n"
                f" Clock Speed: {frequency}"
            )

            self.set_tooltip_if_enabled(tooltip_text)

        return True


class MemoryWidget(FabricatorBoundWidget, StatDisplayMixin):
    """A widget to display the current memory usage."""

    def __init__(
        self,
        **kwargs,
    ):
        # Initialize the Box with specific name and style
        super().__init__(
            name="memory",
            **kwargs,
        )

        # Setup display mode using mixin
        self.setup_stat_display(self.container_box)

        # Set up a fabricator to call the update_label method  at specified intervals
        self._bind_fabricator_changed(self._update_ui)

    def _update_ui(self, _, value: dict):
        # Get the current memory usage
        memory = value.get("memory")
        self.used_memory = memory.used
        self.total_memory = memory.total
        self.percent_used = memory.percent

        # Use mixin to update display
        self.update_stat_display(self.percent_used, f"{self.get_used()}")

        # Update the tooltip with the memory usage details if enabled
        self.set_tooltip_if_enabled(
            f"󰾆 {self.percent_used}%\n{get_text_icon('memory')} {self.ratio()}",
        )

        return True

    def get_used(self):
        return helpers.convert_bytes(self.used_memory, self.config.get("unit", "MB"))

    def get_total(self):
        return helpers.convert_bytes(self.total_memory, self.config.get("unit", "MB"))

    def ratio(self):
        return f"{self.get_used()}/{self.get_total()}"


class StorageWidget(FabricatorBoundWidget, StatDisplayMixin):
    """A widget to display the current storage usage."""

    def __init__(
        self,
        **kwargs,
    ):
        # Initialize the Box with specific name and style
        super().__init__(
            name="storage",
            **kwargs,
        )

        # Setup display mode using mixin
        self.setup_stat_display(self.container_box)

        # Set up a fabricator to call the update_label method at specified intervals
        self._bind_fabricator_changed(self._update_ui)

    def _update_ui(self, _, value: dict):
        # Get the current disk usage
        self.disk = value.get("disk")
        percent = self.disk.percent

        # Use mixin to update display
        self.update_stat_display(percent, f"{self.get_used()}")

        # Update the tooltip with the storage usage details if enabled
        self.set_tooltip_if_enabled(
            f"󰾆 {percent}%\n{get_text_icon('storage')} {self.ratio()}"
        )

        return True

    def get_used(self):
        return helpers.convert_bytes(self.disk.used, self.config.get("unit", "MB"))

    def get_total(self):
        return helpers.convert_bytes(self.disk.total, self.config.get("unit", "MB"))

    def ratio(self):
        return f"{self.get_used()}/{self.get_total()}"


class NetworkUsageWidget(FabricatorBoundWidget):
    """A widget to display the current network usage."""

    def __init__(
        self,
        **kwargs,
    ):
        super().__init__(
            name="network_usage",
            **kwargs,
        )

        self.label_format: str = self.config.get("label_format", "")

        # Thresholds (in bytes/s)
        self.download_threshold = self.config.get("download_threshold", 0)
        self.upload_threshold = self.config.get("upload_threshold", 0)

        # Number of digits for formatting
        self.kb_digits = self.config.get("kb_digits", 0)
        self.mb_digits = self.config.get("mb_digits", 2)

        self.network_label = Label(
            name="network_label", label="0 MB", style_classes="panel-text"
        )

        self.container_box.children = [self.network_label]

        self.client = NetworkSpeed()

        # Cache and interval for network stats (interval in milliseconds)
        self._last_network_poll = 0.0
        self._network_poll_interval = float(self.config.get("interval", 2000)) / 1000.0

        # Set up a fabricator to call the update_label method at specified intervals
        self._bind_fabricator_changed(self._update_ui)

    def format_speed(self, speed: float):
        speed_bps = max(float(speed), 0.0)
        if speed_bps < 1024:
            return f"{speed_bps:.0f} B/s"
        elif speed_bps < 1024 * 1024:
            return f"{speed_bps / 1024:.{self.kb_digits}f} KB/s"
        else:
            return f"{speed_bps / (1024 * 1024):.{self.mb_digits}f} MB/s"

    def _update_ui(self, *_):
        """Update the network usage label with the current network usage."""

        now = monotonic()
        if (now - self._last_network_poll) < self._network_poll_interval:
            return True

        self._last_network_poll = now

        network_speed = self.client.get_network_speed()

        download_speed = network_speed.get("download", 0)
        upload_speed = network_speed.get("upload", 0)

        upload_display = upload_speed if upload_speed >= self.upload_threshold else 0

        download_display = (
            download_speed if download_speed >= self.download_threshold else 0
        )

        label_text = self.label_format.format(
            upload=self.format_speed(upload_display),
            download=self.format_speed(download_display),
        )

        idle_add(self.network_label.set_label, label_text)

        self.set_tooltip_if_enabled(
            f"Download: {self.format_speed(download_speed)}\n"
            f"Upload: {self.format_speed(upload_speed)}"
        )

        return True

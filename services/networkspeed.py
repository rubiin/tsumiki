from time import monotonic

import psutil
from fabric.utils import logger, re

from utils.singleton import SingletonMixin


class NetworkSpeed(SingletonMixin):
    """A service to monitor network speed."""

    __slots__ = (
        "last_sample_time",
        "last_total_down_bytes",
        "last_total_up_bytes",
    )

    _virtual_iface_re = None

    def __init__(self):
        if not self._init_once():
            return
        self.last_total_down_bytes = 0
        self.last_total_up_bytes = 0
        self.last_sample_time = 0.0

    def _get_virtual_iface_re(self):
        if self._virtual_iface_re is None:
            self.__class__._virtual_iface_re = re.compile(
                r"^(ifb|lxdbr|virbr|br|vnet|tun|tap)[0-9]+$"
            )
        return self._virtual_iface_re

    def get_network_speed(self):
        # Read counters from psutil for all interfaces.
        try:
            interface_counters = psutil.net_io_counters(pernic=True)
        except Exception as e:
            logger.warning(f"[NetworkSpeed] Failed to read network counters: {e}")
            return {"download": 0.0, "upload": 0.0}

        total_down_bytes = 0
        total_up_bytes = 0

        for interface, counters in interface_counters.items():
            current_interface_down_bytes = int(counters.bytes_recv)
            current_interface_up_bytes = int(counters.bytes_sent)

            # Skip loopback and virtual interfaces or interfaces with invalid byte count
            if (
                interface == "lo"
                or self._get_virtual_iface_re().match(interface)
                or current_interface_down_bytes < 0
                or current_interface_up_bytes < 0
            ):
                continue

            total_down_bytes += current_interface_down_bytes
            total_up_bytes += current_interface_up_bytes

        # Prime baseline on first sample to avoid a fake spike.
        now = monotonic()
        if self.last_sample_time == 0.0:
            self.last_total_down_bytes = total_down_bytes
            self.last_total_up_bytes = total_up_bytes
            self.last_sample_time = now
            return {"download": 0.0, "upload": 0.0}

        elapsed = max(now - self.last_sample_time, 1e-6)
        down_delta = max(total_down_bytes - self.last_total_down_bytes, 0)
        up_delta = max(total_up_bytes - self.last_total_up_bytes, 0)

        # Return bytes per second, matching common network-rate conventions.
        download_speed = down_delta / elapsed
        upload_speed = up_delta / elapsed

        self.last_total_down_bytes = total_down_bytes
        self.last_total_up_bytes = total_up_bytes
        self.last_sample_time = now

        return {"download": download_speed, "upload": upload_speed}

import contextlib
import shlex
from typing import Any, Literal

import gi
from fabric.core.service import Property, Service, Signal
from fabric.utils import Gio, GLib, bulk_connect, exec_shell_command_async, logger, time

from utils.constants import NETWORK_RECENCY_THRESHOLD_SECONDS
from utils.exceptions import NetworkManagerNotFoundError

from .base import SingletonService

try:
    gi.require_version("NM", "1.0")
    from gi.repository import NM
except ValueError:
    raise NetworkManagerNotFoundError()

_WIFI_STRENGTH_MAP = {
    80: "network-wireless-signal-excellent-symbolic",
    60: "network-wireless-signal-good-symbolic",
    40: "network-wireless-signal-ok-symbolic",
    20: "network-wireless-signal-weak-symbolic",
    0: "network-wireless-signal-none-symbolic",
}
_ACTIVE_CONN_STATE_MAP = {
    NM.ActiveConnectionState.ACTIVATED: "activated",
    NM.ActiveConnectionState.ACTIVATING: "activating",
    NM.ActiveConnectionState.DEACTIVATING: "deactivating",
    NM.ActiveConnectionState.DEACTIVATED: "deactivated",
}
_DEVICE_STATE_MAP = {
    NM.DeviceState.UNMANAGED: "unmanaged",
    NM.DeviceState.UNAVAILABLE: "unavailable",
    NM.DeviceState.DISCONNECTED: "disconnected",
    NM.DeviceState.PREPARE: "prepare",
    NM.DeviceState.CONFIG: "config",
    NM.DeviceState.NEED_AUTH: "need_auth",
    NM.DeviceState.IP_CONFIG: "ip_config",
    NM.DeviceState.IP_CHECK: "ip_check",
    NM.DeviceState.SECONDARIES: "secondaries",
    NM.DeviceState.ACTIVATED: "activated",
    NM.DeviceState.DEACTIVATING: "deactivating",
    NM.DeviceState.FAILED: "failed",
}


class Wifi(Service):
    """A service to manage wifi devices"""

    @Signal
    def changed(self) -> None: ...

    @Signal
    def enabled(self) -> bool: ...

    @Signal
    def scanning(self, is_scanning: bool) -> None: ...

    def __init__(self, client: NM.Client, device: NM.DeviceWifi, **kwargs):
        self._client: NM.Client = client
        self._device: NM.DeviceWifi = device
        self._ap: NM.AccessPoint | None = None
        self._ap_signal: int | None = None
        super().__init__(**kwargs)

        self._client.connect(
            "notify::wireless-enabled",
            lambda *_: self.notifier("enabled"),
        )
        if self._device:
            bulk_connect(
                self._device,
                {
                    "notify::active-access-point": self._activate_ap,
                    "access-point-added": lambda *_: self.emit("changed"),
                    "access-point-removed": lambda *_: self.emit("changed"),
                    "state-changed": self.ap_update,
                },
            )
            self._activate_ap()

    def ap_update(self, *_):
        self.emit("changed")
        for sn in [
            "enabled",
            "internet",
            "strength",
            "frequency",
            "access-points",
            "ssid",
            "state",
            "icon-name",
        ]:
            self.notify(sn)

    def _activate_ap(self, *_):
        if self._ap:
            self._ap.disconnect(self._ap_signal)
        self._ap = self._device.get_active_access_point()
        if not self._ap:
            return

        self._ap_signal = self._ap.connect(
            "notify::strength", lambda *_: self.ap_update()
        )  # type: ignore

    def toggle_wifi(self):
        self._client.wireless_set_enabled(not self._client.wireless_get_enabled())

    def scan(self):
        """Start scanning for WiFi networks and emit scanning signal"""
        if self._device:
            self.emit("scanning", True)  # Emit signal that scanning has started

            def _on_scan_done(device, result):
                with contextlib.suppress(GLib.Error):
                    device.request_scan_finish(result)
                self.emit("scanning", False)

            self._device.request_scan_async(None, _on_scan_done)

    def is_active_ap(self, name) -> bool:
        return self._ap.get_bssid() == name if self._ap else False

    def notifier(self, name: str, *_):
        self.notify(name)
        self.emit("changed")
        return

    def forget_access_point(self, ssid):
        # List saved connections async; each stdout line arrives as its own call.
        def _on_connection_line(line):
            connection_id = line.strip()
            if not connection_id or connection_id != ssid:
                return
            exec_shell_command_async(
                f"nmcli connection delete id {shlex.quote(connection_id)}",
                self._log_nmcli,
            )
            logger.info(f"[NetworkService] Deleted saved connection: {connection_id}")

        exec_shell_command_async("nmcli -g NAME connection show", _on_connection_line)

    def connect_network(self, ssid: str, password: str = "", remember: bool = True):
        """Connect to a WiFi network (async; connection is a side effect)."""
        if not ssid:
            logger.exception("[NetworkService] SSID cannot be empty")
            return
        if password:
            cmd = [
                "nmcli",
                "device",
                "wifi",
                "connect",
                ssid,
                "password",
                password,
            ]
            if not remember:
                cmd.append("--temporary")
            exec_shell_command_async(
                " ".join(shlex.quote(c) for c in cmd), self._log_nmcli
            )
        else:
            exec_shell_command_async(
                f"nmcli con up {shlex.quote(ssid)}", self._log_nmcli
            )

    def disconnect_network(self, ssid: str):
        """Disconnect from a WiFi network (async; side effect only)."""
        if not ssid:
            logger.exception("[NetworkService] SSID cannot be empty")
            return
        # A list, not a shell string: an SSID is a user-chosen name.
        exec_shell_command_async(["nmcli", "con", "down", ssid], self._log_nmcli)

    def _log_nmcli(self, out):
        if out:
            logger.info(f"[NetworkService] nmcli: {out}")

    @Property(bool, "read-write", default_value=False)
    def enabled(self) -> bool:  # noqa: F811
        return bool(self._client.wireless_get_enabled())

    @enabled.setter
    def enabled(self, value: bool):
        self._client.wireless_set_enabled(value)

    @Property(int, "readable")
    def strength(self):
        return self._ap.get_strength() if self._ap else -1

    @Property(str, "readable")
    def icon_name(self):
        if not self._ap:
            return "network-wireless-disabled-symbolic"

        if self.internet == "activated":
            return _WIFI_STRENGTH_MAP.get(
                min(80, 20 * round(self._ap.get_strength() / 20)),
                "network-wireless-no-route-symbolic",
            )
        if self.internet == "activating":
            return "network-wireless-acquiring-symbolic"

        return "network-wireless-offline-symbolic"

    @Property(int, "readable")
    def frequency(self):
        return self._ap.get_frequency() if self._ap else -1

    @Property(int, "readable")
    def internet(self):
        active_connection = self._device.get_active_connection()
        if not active_connection:
            return "disconnected"

        return _ACTIVE_CONN_STATE_MAP.get(
            active_connection.get_state(),
            "unknown",
        )

    def make_ap_dict(self, network_data):
        ap = network_data["ap"]
        ssid = network_data["ssid"]
        strength = network_data["strength"]

        return {
            "bssid": ap.get_bssid(),
            "last_seen": ap.get_last_seen(),
            "wpa_flags": ap.get_wpa_flags(),
            "ssid": ssid,
            "active-ap": self._ap,
            "strength": strength,
            "frequency": ap.get_frequency(),
            "icon-name": _WIFI_STRENGTH_MAP.get(
                min(80, 20 * round(strength / 20)),
                "network-wireless-no-route-symbolic",
            ),
            "secured": self._is_ap_secured(ap),
        }

    def _is_ap_secured(self, ap: NM.AccessPoint) -> bool:
        # NM security flags are non-zero for secured networks.
        return bool(ap.get_wpa_flags() or ap.get_rsn_flags() or ap.get_flags())

    @Property(object, "readable")
    def access_points(self) -> list[object]:
        points: list[NM.AccessPoint] = self._device.get_access_points()

        # Filter and deduplicate access points
        unique_networks = {}
        current_time = time.time()

        for ap in points:
            # Skip if no SSID data
            if not ap.get_ssid():
                continue

            ssid_data = ap.get_ssid().get_data()
            if not ssid_data:
                continue

            ssid = NM.utils_ssid_to_utf8(ssid_data)
            if not ssid or ssid.strip() == "":
                continue

            # Skip hidden networks (empty SSID)
            if ssid == "Unknown":
                continue

            strength = ap.get_strength()
            bssid = ap.get_bssid()
            last_seen = ap.get_last_seen()

            # Add network info for filtering
            network_info = {
                "ap": ap,
                "strength": strength,
                "bssid": bssid,
                "ssid": ssid,
                "last_seen": last_seen,
                "is_recent": last_seen == 0
                or (current_time - last_seen) <= NETWORK_RECENCY_THRESHOLD_SECONDS,
            }

            # For duplicate SSIDs, keep the one with the strongest signal
            # But prioritize recent networks over old ones
            if ssid in unique_networks:
                existing = unique_networks[ssid]
                # Prefer recent networks, then strength
                new_is_more_recent = (
                    network_info["is_recent"] and not existing["is_recent"]
                )
                is_stronger_with_same_recency = (
                    network_info["is_recent"] == existing["is_recent"]
                    and strength > existing["strength"]
                )
                if new_is_more_recent or is_stronger_with_same_recency:
                    unique_networks[ssid] = network_info
            else:
                unique_networks[ssid] = network_info

        # Sort by signal strength (strongest first)
        sorted_networks = sorted(
            unique_networks.values(), key=lambda x: x["strength"], reverse=True
        )

        return list(map(self.make_ap_dict, sorted_networks))

    @Property(str, "readable")
    def ssid(self):
        if not self._ap:
            return "Disconnected"
        ssid = self._ap.get_ssid().get_data()
        return NM.utils_ssid_to_utf8(ssid) if ssid else "Unknown"

    @Property(int, "readable")
    def state(self):
        return _DEVICE_STATE_MAP.get(self._device.get_state(), "unknown")


class Ethernet(Service):
    """A service to manage ethernet devices"""

    @Signal
    def changed(self) -> None: ...

    @Signal
    def enabled(self) -> bool: ...

    @Property(int, "readable")
    def speed(self) -> int:
        return self._device.get_speed()

    @Property(str, "readable")
    def internet(self) -> str:
        active_connection = self._device.get_active_connection()
        if not active_connection:
            return "disconnected"

        return _ACTIVE_CONN_STATE_MAP.get(
            active_connection.get_state(),
            "disconnected",
        )

    @Property(str, "readable")
    def icon_name(self) -> str:
        network = self.internet
        if network == "activated":
            return "network-wired-symbolic"

        elif network == "activating":
            return "network-wired-acquiring-symbolic"

        elif self._device.get_connectivity != NM.ConnectivityState.FULL:
            return "network-wired-no-route-symbolic"

        return "network-wired-disconnected-symbolic"

    def __init__(self, client: NM.Client, device: NM.DeviceEthernet, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client: NM.Client = client
        self._device: NM.DeviceEthernet = device

        for names in (
            "active-connection",
            "icon-name",
            "internet",
            "speed",
            "state",
        ):
            self._device.connect(f"notify::{names}", self._on_device_notify, names)

    def _on_device_notify(self, _device, _param_spec, prop_name: str):
        self.notifier(prop_name)

    def notifier(self, names):
        self.notify(names)
        self.emit("changed")


class NetworkService(SingletonService):
    """A service to manage network devices"""

    @Signal
    def device_ready(self) -> None: ...

    def __init__(self, **kwargs):
        self._client: NM.Client | None = None
        self.wifi_device: Wifi | None = None
        self.ethernet_device: Ethernet | None = None
        self._last_primary_device: Literal["wifi", "wired"] | None = None
        super().__init__(**kwargs)
        NM.Client.new_async(
            cancellable=None,
            callback=self._init_network_client,
            **kwargs,
        )

    def _init_network_client(self, client: NM.Client, task: Gio.Task, **kwargs):
        self._client = client

        for signal_name in (
            "notify::primary-connection",
            "notify::connectivity",
            "notify::wireless-enabled",
        ):
            self._client.connect(signal_name, self._on_client_state_changed)

        wifi_device: NM.DeviceWifi | None = self._get_device(NM.DeviceType.WIFI)  # type: ignore
        ethernet_device: NM.DeviceEthernet | None = self._get_device(
            NM.DeviceType.ETHERNET
        )

        if wifi_device:
            self.wifi_device = Wifi(self._client, wifi_device)
            self.emit("device-ready")

        if ethernet_device:
            self.ethernet_device = Ethernet(client=self._client, device=ethernet_device)
            self.emit("device-ready")

        self._notify_primary_device_changed(force=True)

    def _on_client_state_changed(self, *_):
        self._notify_primary_device_changed()

    def _notify_primary_device_changed(self, force: bool = False):
        current_primary_device = self._get_primary_device()
        if not force and current_primary_device == self._last_primary_device:
            return

        self._last_primary_device = current_primary_device
        self.notify("primary-device")
        # Keep existing refresh contract used by quick settings consumers.
        self.emit("device-ready")

    def _get_device(self, device_type) -> Any:
        devices: list[NM.Device] = self._client.get_devices()  # type: ignore
        return next(
            (x for x in devices if x.get_device_type() == device_type),
            None,
        )

    def _get_primary_device(self) -> Literal["wifi", "wired"] | None:
        if not self._client:
            return None

        if self._client.get_primary_connection() is None:
            return "wifi"
        return (
            "wifi"
            if "wireless"
            in str(self._client.get_primary_connection().get_connection_type())
            else "wired"
            if "ethernet"
            in str(self._client.get_primary_connection().get_connection_type())
            else None
        )

    @Property(str, "readable")
    def primary_device(self) -> Literal["wifi", "wired"] | None:
        return self._get_primary_device()

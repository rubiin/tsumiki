from __future__ import annotations

import json
from datetime import datetime
from ipaddress import ip_address

from fabric.utils import idle_add, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget
from utils.functions import get_http_client, run_in_thread
from utils.i18n import _
from utils.widget_utils import nerd_font_icon


class IPMonitorPopoverContent(Box):
    """Popup content that mirrors the Noctalia IP monitor preview."""

    def __init__(self, config: dict, parent=None, **kwargs):
        super().__init__(
            name="ip-monitor-window",
            orientation="v",
            spacing=8,
            **kwargs,
        )

        self._parent = parent
        self._config = config.get("widgets", {}).get("ip_monitor", {})
        self._last_updated = None

        self._request_generation = 0
        self._state: dict[str, str] = {
            "ip": "-",
            "hostname": "-",
            "city": "-",
            "region": "-",
            "country": "-",
            "country_code": "-",
            "latitude": "-",
            "longitude": "-",
            "postal": "-",
            "timezone": "-",
            "org": "-",
        }

        self._build_ui()
        self._apply_state()
        self.refresh(force=True)

    def _build_ui(self):
        self.title = Label(
            label=_("widget.ip_monitor.tooltip"),
            style_classes="ip-monitor-title",
            h_align="start",
            h_expand=True,
        )

        self.refresh_btn = Button(
            name="ip-monitor-refresh-btn",
            style_classes="ip-monitor-refresh-btn",
            child=Box(
                spacing=6,
                children=[
                    nerd_font_icon(
                        icon="",
                        props={"style_classes": ["ip-monitor-refresh-icon"]},
                    ),
                    Label(
                        label=_("common.refresh"),
                        style_classes="ip-monitor-refresh-label",
                    ),
                ],
            ),
            on_clicked=self._on_refresh_clicked,
        )

        self.header = Box(
            name="ip-monitor-header",
            orientation="h",
            spacing=8,
            children=[self.title, self.refresh_btn],
        )

        self.hero_icon = nerd_font_icon(
            icon="󰖟",
            props={"style_classes": ["ip-monitor-hero-icon"]},
        )
        self.hero_ip = Label(
            label="-",
            style_classes="ip-monitor-hero-ip",
            h_align="center",
        )
        self.hero_location = Label(
            label="-",
            style_classes="ip-monitor-hero-location",
            h_align="center",
        )

        self.hero_card = Box(
            name="ip-monitor-hero-card",
            orientation="v",
            spacing=4,
            h_align="fill",
            children=[self.hero_icon, self.hero_ip, self.hero_location],
        )

        self.details_title = Label(
            label=_("common.details"),
            style_classes="ip-monitor-section-title",
            h_align="start",
        )

        self.details_box = Box(
            name="ip-monitor-details-card",
            orientation="v",
            spacing=4,
            children=[],
        )

        self.detail_value_labels: dict[str, Label] = {}
        for field_key, field_label in [
            ("ip", "IP Address"),
            ("hostname", "Hostname"),
            ("city", "City"),
            ("region", "Region"),
            ("country", "Country"),
            ("location", "Location"),
            ("postal", "Postal Code"),
            ("timezone", "Timezone"),
            ("org", "Organization"),
        ]:
            key_label = Label(
                label=f"{field_label}:",
                style_classes="ip-monitor-detail-key",
                h_align="start",
            )
            value_label = Label(
                label="-",
                style_classes="ip-monitor-detail-value",
                h_align="start",
            )
            row = Box(
                orientation="h",
                spacing=8,
                children=[key_label, value_label],
            )
            self.details_box.add(row)
            self.detail_value_labels[field_key] = value_label

        self.last_updated = Label(
            label="",
            style_classes="ip-monitor-last-updated",
            h_align="end",
        )

        self.children = [
            self.header,
            self.hero_card,
            self.details_title,
            self.details_box,
            self.last_updated,
        ]

    def _normalize_value(self, value: object) -> str:
        text = str(value).strip() if value is not None else ""
        return text if text else "-"

    def _apply_state(self):
        ip = self._state.get("ip", "-")
        city = self._state.get("city", "-")
        country_code = self._state.get("country_code", "-")

        location_label = city
        if country_code not in {"", "-"}:
            location_label = f"{city}, {country_code}"

        self.hero_ip.set_label(ip)
        self.hero_location.set_label(location_label)

        self.detail_value_labels["ip"].set_label(ip)
        self.detail_value_labels["hostname"].set_label(self._state.get("hostname", "-"))
        self.detail_value_labels["city"].set_label(city)
        self.detail_value_labels["region"].set_label(self._state.get("region", "-"))

        country_text = self._state.get("country", "-")
        if country_code not in {"", "-"} and country_text not in {"", "-"}:
            country_text = f"{country_text} ({country_code})"
        self.detail_value_labels["country"].set_label(country_text)

        lat = self._state.get("latitude", "-")
        lon = self._state.get("longitude", "-")
        location = "-" if lat == "-" or lon == "-" else f"{lat}, {lon}"
        self.detail_value_labels["location"].set_label(location)

        self.detail_value_labels["postal"].set_label(self._state.get("postal", "-"))
        self.detail_value_labels["timezone"].set_label(self._state.get("timezone", "-"))
        self.detail_value_labels["org"].set_label(self._state.get("org", "-"))

        if self._last_updated is not None:
            self.last_updated.set_label(f"Updated {self._last_updated}")

    def _fetch_ip_info(self) -> dict[str, str]:
        ipv4_addr = "-"

        try:
            response = get_http_client().get(
                "https://api.ipify.org?format=json", timeout=6
            )
            ipv4_data = json.loads(response.text)
            candidate = self._normalize_value(
                ipv4_data.get("ip") if isinstance(ipv4_data, dict) else None
            )
            if candidate not in {"", "-"} and ip_address(candidate).version == 4:
                ipv4_addr = candidate
        except Exception as e:
            logger.debug(f"[ip_monitor] Failed to get public IP: {e}")
            ipv4_addr = "-"

        endpoint_template = "https://ipapi.co/{ip}/json/"

        if "{ip}" in endpoint_template:
            endpoint = (
                endpoint_template.format(ip=ipv4_addr)
                if ipv4_addr != "-"
                else "https://ipapi.co/json/"
            )
        else:
            endpoint = (
                f"https://ipapi.co/{ipv4_addr}/json/"
                if ipv4_addr != "-"
                else endpoint_template
            )

        response = get_http_client().get(endpoint, timeout=8)
        data = json.loads(response.text)

        if not isinstance(data, dict):
            raise ValueError("IP API returned unexpected payload")

        return {
            "ip": (
                ipv4_addr if ipv4_addr != "-" else self._normalize_value(data.get("ip"))
            ),
            "hostname": self._normalize_value(data.get("hostname")),
            "city": self._normalize_value(data.get("city")),
            "region": self._normalize_value(data.get("region")),
            "country": self._normalize_value(
                data.get("country_name") or data.get("country")
            ),
            "country_code": self._normalize_value(data.get("country_code")),
            "latitude": self._normalize_value(data.get("latitude")),
            "longitude": self._normalize_value(data.get("longitude")),
            "postal": self._normalize_value(data.get("postal")),
            "timezone": self._normalize_value(data.get("timezone")),
            "org": self._normalize_value(data.get("org")),
        }

    @run_in_thread
    def _refresh_async(self, generation: int):
        try:
            state = self._fetch_ip_info()
            idle_add(self._apply_refresh_result, generation, state)
        except Exception as err:
            logger.warning(f"[ip_monitor] Failed to refresh IP info: {err}")
            idle_add(self._set_error_state, generation, str(err))

    def _apply_refresh_result(self, generation: int, state: dict[str, str]):
        if generation != self._request_generation:
            return False

        self._state.update(state)
        self._last_updated = datetime.now().strftime("%H:%M:%S")
        self._apply_state()
        return False

    def _set_error_state(self, generation: int, error: str):
        if generation != self._request_generation:
            return False

        self._last_updated = "failed"
        self.last_updated.set_label(f"Update failed: {error[:60]}")
        return False

    def refresh(self, force: bool = False):
        if not force and self._request_generation > 0:
            return

        self._request_generation += 1
        self._refresh_async(self._request_generation)

    def _on_refresh_clicked(self, *_):
        self.refresh(force=True)


class IPMonitorWidget(ButtonWidget, PopoverMixin):
    """Bar widget for showing IP information."""

    def __init__(self, **kwargs):
        super().__init__(name="ip_monitor", **kwargs)

        self.add_panel_content(
            self.config.get("icon", "󰖟"),
            self.config.get("label_text", "IP"),
            show_label=self.config.get("label", False),
        )

        self.set_tooltip_if_enabled(_("widget.ip_monitor.tooltip"), default=True)

        self.setup_popover(
            lambda: IPMonitorPopoverContent(
                config={"widgets": {"ip_monitor": self.config}},
                parent=self,
            ),
            connect_clicked=False,
        )
        self.connect("clicked", self._on_click)

    def _on_click(self, *_):
        popup = self.popup
        if popup and hasattr(popup, "content") and hasattr(popup.content, "refresh"):
            popup.content.refresh(force=False)
        self.toggle_popover()

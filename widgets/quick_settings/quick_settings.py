import os

from fabric.utils import GLib, Gtk, invoke_repeater, logger
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.grid import Grid
from fabric.widgets.label import Label

import utils.functions as helpers
from services import (
    audio_service,
)
from services.brightness import BrightnessService
from services.network import NetworkService, Wifi
from shared.buttons import HoverButton, QSChevronButton
from shared.circle_image import CircularImage
from shared.dialog import Dialog
from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget
from utils.constants import ASSETS_DIR
from utils.functions import expand_env, lazy_load_class, safe_disconnect
from utils.i18n import _
from utils.icons import get_text_icon, network_icon_to_text_icons
from utils.widget_utils import (
    get_audio_icon_name,
    get_brightness_icon_name,
    nerd_font_icon,
    uptime,
)

from .components import LazyWidgetContainer
from .shortcuts import ShortcutsContainer
from .submenu.audio import AudioSubMenu
from .togglers import (
    DarkModeToggle,
    FlightModeToggle,
    HyprIdleQuickSetting,
    NotificationQuickSetting,
)

_WIFI_GENERIC_ICON = get_text_icon("wifi.generic", "󰤬")
_ETHERNET_ICON = get_text_icon("ethernet", "󰈀")
_BRIGHTNESS_MEDIUM_ICON = get_text_icon("brightness.medium", "󰃟")
_HOURGLASS_ICON = get_text_icon("hourglass", "")

_DEFAULT_TOGGLES = [
    "wifi",
    "bluetooth",
    "power_profiles",
    "hyprsunset",
    "hypridle",
    "notification",
]


class QuickSettingsButtonBox(Box):
    """A box to display the quick settings buttons."""

    @staticmethod
    def _build_toggle(
        module_path: str,
        submenu_cls_name: str,
        toggle_cls_name: str,
        **kwargs,
    ):
        submenu_cls = lazy_load_class(module_path, submenu_cls_name)
        toggle_cls = lazy_load_class(module_path, toggle_cls_name)
        return toggle_cls(submenu_factory=submenu_cls, **kwargs)

    def _create_toggle(self, name: str):
        """Build a quick settings toggle by name, or None if unknown."""
        if name == "wifi":
            return self._build_toggle(
                "widgets.quick_settings.submenu.wifi",
                "WifiSubMenu",
                "WifiToggle",
            )
        if name == "bluetooth":
            return self._build_toggle(
                "widgets.quick_settings.submenu.bluetooth",
                "BluetoothSubMenu",
                "BluetoothToggle",
            )
        if name == "power_profiles":
            return self._build_toggle(
                "widgets.quick_settings.submenu.power_profiles",
                "PowerProfileSubMenu",
                "PowerProfileToggle",
                popup=self.popup,
            )
        if name == "hyprsunset":
            return self._build_toggle(
                "widgets.quick_settings.submenu.hyprsunset",
                "HyprSunsetSubMenu",
                "HyprSunsetToggle",
                popup=self.popup,
            )
        if name == "hypridle":
            return HyprIdleQuickSetting(popup=self.popup)
        if name == "notification":
            return NotificationQuickSetting(popup=self.popup)
        if name == "darkmode":
            return DarkModeToggle(popup=self.popup)
        if name == "flightmode":
            return FlightModeToggle(popup=self.popup)
        logger.warning(f"Unknown quick settings toggle: {name}")
        return None

    def close_all_submenus(self, *_):
        if self.active_submenu is not None:
            self.active_submenu._reveal(False)
            self.active_submenu = None

    def __init__(self, popup, toggles=None, **kwargs):
        super().__init__(
            orientation="v",
            name="quick-settings-button-box",
            spacing=4,
            v_align="start",
            v_expand=True,
            **kwargs,
        )

        self.popup = popup
        self.toggles = _DEFAULT_TOGGLES if toggles is None else toggles

        self.grid = Grid(
            row_spacing=10,
            column_spacing=10,
            column_homogeneous=True,
            row_homogeneous=True,
        )

        self.active_submenu = None

        built_toggles = []
        for name in self.toggles:
            toggle = self._create_toggle(name)
            if toggle is not None:
                built_toggles.append(toggle)

        # Toggles flow left-to-right, two per row; the last odd toggle spans
        # the full row width so there's no dangling half-width card.
        for i, toggle in enumerate(built_toggles):
            if i == len(built_toggles) - 1 and len(built_toggles) % 2 == 1:
                self.grid.attach(toggle, 0, i // 2, 2, 1)
            else:
                self.grid.attach(toggle, i % 2, i // 2, 1, 1)

        for toggle in built_toggles:
            if hasattr(toggle, "ensure_submenu"):
                toggle.connect("reveal-clicked", self.set_active_submenu)

        self.children = (self.grid,) if built_toggles else ()

        self.connect("unmap", self.close_all_submenus)

    def set_active_submenu(self, btn: QSChevronButton):
        submenu = btn.ensure_submenu()
        if submenu is None:
            return

        if submenu.get_parent() is None:
            self.add(submenu)

        if submenu != self.active_submenu and self.active_submenu is not None:
            self.active_submenu._reveal(False)

        self.active_submenu = submenu
        self.active_submenu.toggle_reveal()


class QuickSettingsMenu(Box):
    """A menu to display the quick settings information."""

    def _create_power_button(self, icon_name: str, title: str, body: str, command: str):
        return HoverButton(
            child=nerd_font_icon(
                icon=get_text_icon(icon_name),
                props={"style_classes": ["panel-font-icon"]},
            ),
            v_align="center",
            on_clicked=lambda *_: self.show_dialog(
                title=title,
                body=body,
                command=command,
            ),
        )

    def __init__(self, config: dict, popup, **kwargs):
        super().__init__(
            name="quicksettings-menu", orientation="v", all_visible=True, **kwargs
        )

        self.config = config
        self.popup = popup

        user_config = self.config.get("user", {})
        shortcuts_config = self.config.get("shortcuts", {})
        controls_config = self.config.get("controls", {})

        raw_avatar_path = user_config.get("avatar", "$HOME/.face")
        avatar_path = expand_env(raw_avatar_path)
        default_image = f"{ASSETS_DIR}/images/banner.jpg"
        user_image = avatar_path if os.path.exists(avatar_path) else default_image
        if user_image == default_image:
            logger.warning(f"Avatar not found: {avatar_path}")

        username = user_config.get("name", "system")
        username_label = GLib.get_user_name() if username == "system" else username

        if user_config.get("distro_icon", True):
            username_label = f"{helpers.get_distro_icon()} {username_label}"

        username_label = Label(
            label=username_label,
            v_align="center",
            h_align="start",
            style_classes="user",
        )

        uptime_label = Label(
            label=f"{_HOURGLASS_ICON} {uptime()}",
            style_classes="uptime",
            v_align="center",
            h_align="start",
            tooltip_text=_("widget.quick_settings.uptime"),
        )
        self._last_uptime_text = uptime_label.get_label()

        self.user_box = Grid(
            column_spacing=10,
            name="user-box-grid",
            h_expand=True,
        )

        avatar = CircularImage(
            image_file=user_image,
            size=65,
        )

        avatar.set_size_request(65, 65)

        self.user_box.attach(
            avatar,
            0,
            0,
            2,
            2,
        )

        button_box = Box(
            orientation="h",
            h_align="start",
            v_align="center",
            name="button-box",
            h_expand=True,
            v_expand=True,
        )

        button_box.pack_end(
            self._create_power_button(
                "power_menu.reboot",
                _("widget.power.reboot"),
                _("widget.power.confirm_reboot"),
                "reboot",
            ),
            False,
            False,
            5,
        )
        button_box.pack_end(
            self._create_power_button(
                "power_menu.shutdown",
                _("widget.power.shutdown"),
                _("widget.power.confirm_shutdown"),
                "shutdown",
            ),
            False,
            False,
            0,
        )

        self.user_box.attach_next_to(
            username_label, avatar, Gtk.PositionType.RIGHT, 1, 1
        )

        self.user_box.attach_next_to(
            uptime_label, username_label, Gtk.PositionType.BOTTOM, 1, 1
        )

        self.user_box.attach_next_to(
            button_box,
            username_label,
            Gtk.PositionType.RIGHT,
            4,
            4,
        )

        # Create sliders container
        sliders_box = Box(
            orientation="v",
            spacing=10,
            h_expand=True,
        )

        slider_factory = {
            "brightness": (
                "widgets.quick_settings.sliders.brightness",
                "BrightnessSlider",
            ),
            "volume": ("widgets.quick_settings.sliders.audio", "AudioSlider"),
            "microphone": (
                "widgets.quick_settings.sliders.mic",
                "MicrophoneSlider",
            ),
            "mic": ("widgets.quick_settings.sliders.mic", "MicrophoneSlider"),
        }

        for slider_name in controls_config.get("sliders", []):
            slider_path = slider_factory.get(slider_name)
            if not slider_path:
                logger.warning(f"Unknown quick settings slider: {slider_name}")
                continue

            slider_cls = lazy_load_class(*slider_path)
            if slider_name == "volume":
                sliders_box.add(slider_cls(show_chevron=True))
            else:
                sliders_box.add(slider_cls())

        # Per-app audio submenu, revealed by the volume slider's chevron.
        if "volume" in controls_config.get("sliders", []):
            self.audio_submenu = AudioSubMenu()
            sliders_box.audio_submenu = self.audio_submenu
            sliders_box.add(self.audio_submenu)

        # Determine slider box class and main grid based on shortcuts
        shortcuts_enabled = shortcuts_config.get("enabled", False)
        shortcuts_items = shortcuts_config.get("items", [])
        if shortcuts_enabled:
            num_shortcuts = len(shortcuts_items)
            if 2 < num_shortcuts <= 4:
                slider_class = "slider-box-shorter"
            elif 0 < num_shortcuts <= 2:
                slider_class = "slider-box-short"
            else:
                slider_class = "slider-box-long"
            sliders_box.v_expand = True
        else:
            slider_class = "slider-box-long"

        sliders_box.add_style_class(slider_class)

        # Create main grid with sliders and shortcuts if configured
        main_grid = Grid(
            column_spacing=10,
            h_expand=True,
            style_classes="section-box",
        )

        if shortcuts_enabled:
            shortcuts_box = Box(
                orientation="v",
                spacing=10,
                style_classes=["section-box", "shortcuts-box"],
                children=(
                    ShortcutsContainer(
                        shortcuts_config=shortcuts_items,
                        style_classes="shortcuts-grid",
                        v_align="start",
                        h_align="fill",
                    ),
                ),
                h_expand=False,
                v_expand=True,
            )

            main_grid.attach(sliders_box, 0, 0, 2, 1)
            main_grid.attach(shortcuts_box, 2, 0, 1, 1)
        else:
            main_grid.attach(sliders_box, 0, 0, 3, 1)
        toggles = self.config.get("toggles", _DEFAULT_TOGGLES)

        # An empty toggles list hides the toggle section entirely.
        start_children = [self.user_box]
        if toggles:
            start_children.append(QuickSettingsButtonBox(popup=popup, toggles=toggles))

        box = CenterBox(
            orientation="v",
            style_classes="quick-settings-box",
            start_children=Box(
                orientation="v",
                spacing=10,
                v_align="center",
                style_classes="section-box",
                children=start_children,
            ),
            center_children=main_grid,
        )

        if self.config.get("media", {}).get("enabled", False):
            media_config = self.config.get("media", {})

            box.end_children = (
                LazyWidgetContainer(
                    orientation="v",
                    spacing=10,
                    style_classes=["section-box", "quicksettings-media-section"],
                    factory=lambda: lazy_load_class("shared.media", "PlayerBoxStack")(
                        lazy_load_class("services.mpris", "MprisPlayerManager")(),
                        config=media_config,
                    ),
                ),
            )

        self.add(box)

        def _update_uptime(*_):
            uptime_text = f"{_HOURGLASS_ICON} {uptime()}"
            if uptime_text == self._last_uptime_text:
                return True
            self._last_uptime_text = uptime_text
            uptime_label.set_label(uptime_text)
            return True

        # Register a repeater to update uptime every minute
        self._uptime_repeater_id = invoke_repeater(60000, _update_uptime)

    def destroy(self):
        if getattr(self, "_uptime_repeater_id", None) is not None:
            GLib.source_remove(self._uptime_repeater_id)
            self._uptime_repeater_id = None
        return super().destroy()

    def show_dialog(self, title: str, body: str, command: str):
        """Show a dialog with the given title and body."""
        self.get_parent().set_visible(False)
        self.popup.hide_popover()

        Dialog().add_content(
            title=title,
            body=body,
            command=command,
        ).toggle_popup()


class QuickSettingsButtonWidget(ButtonWidget, PopoverMixin):
    """A button to display the date and time."""

    def __init__(self, **kwargs):
        super().__init__(name="quick_settings", **kwargs)

        self._active_wifi = None
        self._wifi_changed_handler_id = None
        self._active_speaker = None
        self._speaker_volume_handler_id = None

        self.audio_service = audio_service

        self.network_service = NetworkService()

        self.brightness_service = BrightnessService()

        self._register_handler(
            self.brightness_service,
            self.brightness_service.connect(
                "brightness_changed", self.update_brightness
            ),
        )

        self._register_handler(
            self.network_service,
            self.network_service.connect("device-ready", self._get_network_icon),
        )

        self.popup = None

        self.audio_icon = nerd_font_icon(
            icon=get_text_icon("volume.medium", "󰖀"),
            props={"style_classes": ["panel-font-icon"]},
        )

        self.network_icon = nerd_font_icon(
            icon=_WIFI_GENERIC_ICON,
            props={"style_classes": ["panel-font-icon"]},
        )

        self.brightness_icon = nerd_font_icon(
            icon=_BRIGHTNESS_MEDIUM_ICON,
            props={"style_classes": ["panel-font-icon"]},
        )

        self._last_network_icon = None
        self._last_audio_icon = None
        self._last_brightness_icon = None

        self.update_brightness()

        self.children = Box(
            children=(
                self.network_icon,
                self.audio_icon,
                self.brightness_icon,
            )
        )

        self._register_handler(
            self.audio_service,
            self.audio_service.connect("notify::speaker", self.on_speaker_changed),
        )
        self._register_handler(
            self.audio_service,
            self.audio_service.connect("changed", self.check_mute),
        )

        self.setup_popover(
            lambda: QuickSettingsMenu(config=self.config, popup=self._popup),
            connect_clicked=True,
            on_close_callback=lambda *_: self.remove_style_class("active"),
        )

    def _get_network_icon(self, *_):
        # Check if the network service is ready
        if self.network_service.primary_device == "wifi":
            wifi = self.network_service.wifi_device
            if wifi:
                self._set_network_icon_from_name(wifi.get_property("icon-name"))
                if (
                    self._active_wifi
                    and self._wifi_changed_handler_id is not None
                    and self._active_wifi != wifi
                ):
                    safe_disconnect(self._active_wifi, self._wifi_changed_handler_id)
                    self._wifi_changed_handler_id = None

                if self._wifi_changed_handler_id is None:
                    self._wifi_changed_handler_id = wifi.connect(
                        "changed", self.update_wifi_status
                    )
                    self._active_wifi = wifi
            else:
                self._set_default_network_icon()
        else:
            ethernet = self.network_service.ethernet_device
            if self._active_wifi and self._wifi_changed_handler_id is not None:
                safe_disconnect(self._active_wifi, self._wifi_changed_handler_id)
                self._wifi_changed_handler_id = None
                self._active_wifi = None
            if ethernet:
                self._set_network_icon(_ETHERNET_ICON)
            else:
                self._set_default_network_icon()

    def _set_network_icon(self, icon_text):
        if icon_text == self._last_network_icon:
            return
        self._last_network_icon = icon_text
        self.network_icon.set_label(icon_text)

    def _set_default_network_icon(self):
        self._set_network_icon(_WIFI_GENERIC_ICON)

    def _set_network_icon_from_name(self, icon_name):
        self._set_network_icon(
            network_icon_to_text_icons.get(
                icon_name,
                _WIFI_GENERIC_ICON,
            )
        )

    def update_wifi_status(self, wifi: Wifi):
        self._set_network_icon_from_name(wifi.get_property("icon-name"))

    def on_speaker_changed(self, *_):
        # Update the progress bar value based on the speaker volume
        speaker = self.audio_service.speaker
        if not speaker:
            return

        if (
            self._active_speaker
            and self._speaker_volume_handler_id is not None
            and self._active_speaker != speaker
        ):
            safe_disconnect(self._active_speaker, self._speaker_volume_handler_id)
            self._speaker_volume_handler_id = None

        if self._speaker_volume_handler_id is None:
            self._speaker_volume_handler_id = speaker.connect(
                "notify::volume", self.update_volume
            )
            self._active_speaker = speaker

        self.update_volume()

    def _set_audio_icon(self, icon_text):
        if icon_text == self._last_audio_icon:
            return
        self._last_audio_icon = icon_text
        self.audio_icon.set_label(icon_text)

    def check_mute(self, *_):
        if not self.audio_service.speaker:
            return
        self._set_audio_icon(
            get_audio_icon_name(
                self.audio_service.speaker.volume, self.audio_service.speaker.muted
            )["icon_text"]
        )

    def update_volume(self, *_):
        if self.audio_service.speaker:
            volume = round(self.audio_service.speaker.volume)
            self._set_audio_icon(
                get_audio_icon_name(volume, self.audio_service.speaker.muted)[
                    "icon_text"
                ]
            )

    def _set_brightness_icon(self, icon_text):
        if icon_text == self._last_brightness_icon:
            return
        self._last_brightness_icon = icon_text
        self.brightness_icon.set_label(icon_text)

    def update_brightness(self, *_):
        """Update the brightness icon."""
        try:
            normalized_brightness = self.brightness_service.screen_brightness_percentage
            icon_info = get_brightness_icon_name(normalized_brightness)["icon_text"]
            if icon_info:
                self._set_brightness_icon(icon_info)
            else:
                # Fallback icon if something goes wrong
                self._set_brightness_icon(_BRIGHTNESS_MEDIUM_ICON)
        except Exception as e:
            logger.exception(f"Error updating brightness icon: {e}")
            # Fallback icon if something goes wrong
            self._set_brightness_icon(_BRIGHTNESS_MEDIUM_ICON)

    def destroy(self):
        if self._active_wifi and self._wifi_changed_handler_id is not None:
            safe_disconnect(self._active_wifi, self._wifi_changed_handler_id)
            self._wifi_changed_handler_id = None
        self._active_wifi = None

        if self._active_speaker and self._speaker_volume_handler_id is not None:
            safe_disconnect(self._active_speaker, self._speaker_volume_handler_id)
            self._speaker_volume_handler_id = None
        self._active_speaker = None

        return super().destroy()

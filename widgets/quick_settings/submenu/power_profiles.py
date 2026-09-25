from collections.abc import Callable

from fabric.widgets.box import Box
from fabric.widgets.label import Label

from services import power_pfl_service
from shared.buttons import HoverButton, QSChevronButton
from shared.submenu import QuickSubMenu
from utils.i18n import _
from utils.icons import get_text_icon
from utils.widget_utils import nerd_font_icon

_ICON_MAP = {"power-saver": "󰌪", "performance": "󰓅", "balanced": "󰒂"}


def icon_name_to_icon(icon_name: str) -> str:
    """Convert icon name to actual icon."""
    return _ICON_MAP.get(icon_name, "󰌪")


class PowerProfileItem(HoverButton):
    """A button to display the power profile."""

    def __init__(
        self,
        profile,
        active,
        **kwargs,
    ):
        self.profile = profile
        self._content_box = Box(
            orientation="h",
            spacing=10,
            children=(
                nerd_font_icon(
                    icon=icon_name_to_icon(profile),
                    props={
                        "style_classes": [
                            "panel-font-icon",
                        ],
                    },
                ),
                Label(
                    label=profile,
                    style_classes="submenu-item-label",
                ),
            ),
        )

        super().__init__(
            style_classes=["submenu-button", "power-profile"],
            child=self._content_box,
            **kwargs,
        )

        self.connect(
            "button-press-event",
            self._handle_click,
        )
        self.set_active(active)

    def _handle_click(self, *_):
        power_pfl_service.active_profile = self.profile
        return True

    def set_active(self, active: str):
        if self.profile == active:
            self._content_box.add_style_class("active")
        else:
            self._content_box.remove_style_class("active")


class PowerProfileSubMenu(QuickSubMenu):
    """A submenu to display power profile options."""

    def __init__(self, **kwargs):
        self.profiles = [profile["Profile"] for profile in power_pfl_service.profiles]

        self.profile_items = None
        self.scan_button = None

        self.profile_box = Box(
            orientation="v",
            name="power-profile-container",
            spacing=8,
            style_classes="power-profile-container",
        )

        super().__init__(
            title=_("widget.quick_settings.power_profiles.title"),
            title_icon=get_text_icon("powerprofiles.power-saver", "󰌪"),
            scan_button=self.scan_button,
            child=self.profile_box,
            **kwargs,
        )

        # Listen for profile changes once; the base class already wires the
        # revealer to ``on_child_revealed``.
        self._profile_changed_handler = power_pfl_service.connect(
            "changed", self.on_profile_changed
        )
        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, *_):
        if self._profile_changed_handler is not None:
            from utils.functions import safe_disconnect

            safe_disconnect(power_pfl_service, self._profile_changed_handler)
            self._profile_changed_handler = None

    def on_child_revealed(self, *_):
        """Callback when the submenu is revealed."""

        if self.profile_items is None:
            self.profile_items = [
                PowerProfileItem(
                    profile=profile, active=power_pfl_service.active_profile
                )
                for profile in self.profiles
            ]

            self.profile_box.children = self.profile_items
        else:
            # Keep the items in sync with the current profile.
            self.on_profile_changed()

    def on_profile_changed(self, *_):
        if self.profile_items is None:
            return
        active = power_pfl_service.active_profile
        for item in self.profile_items:
            item.set_active(active)


class PowerProfileToggle(QSChevronButton):
    """A widget to display a toggle button for Wifi."""

    def __init__(
        self,
        submenu_factory: Callable[[], QuickSubMenu] | None = None,
        popup=None,
        **kwargs,
    ):
        super().__init__(
            action_icon=get_text_icon("powerprofiles.power-saver", "󰌪"),
            action_label=_("widget.quick_settings.power_profiles.saver"),
            submenu_factory=submenu_factory,
            **kwargs,
        )
        self.popup = popup

        self.update_action_button()
        self.set_active_style(True)
        self.action_button.set_sensitive(False)

        self._register_handlers(
            power_pfl_service,
            {"changed": self.update_action_button},
        )

    def unslug(self, text: str) -> str:
        return " ".join([word.capitalize() for word in text.split("-")])

    def update_action_button(self, *_):
        active = power_pfl_service.active_profile
        self.action_icon.set_label(icon_name_to_icon(active))
        self.set_action_label(self.unslug(active))

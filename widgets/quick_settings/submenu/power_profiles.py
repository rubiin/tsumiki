from collections.abc import Callable

from fabric.utils import Gtk
from fabric.widgets.box import Box
from fabric.widgets.label import Label

from services import power_profile_service
from shared.buttons import QSChevronButton
from shared.list import ListBox, add_list_row
from shared.submenu import QuickSubMenu
from utils.i18n import _
from utils.icons import get_text_icon
from utils.widget_utils import nerd_font_icon, setup_cursor_hover

_ICON_MAP = {"power-saver": "󰌪", "performance": "󰓅", "balanced": "󰒂"}


def icon_name_to_icon(icon_name: str) -> str:
    """Convert icon name to actual icon."""
    return _ICON_MAP.get(icon_name, "󰌪")


class PowerProfileItem(Gtk.ListBoxRow):
    """A row to display the power profile."""

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

        super().__init__(visible=True, **kwargs)
        style_context = self.get_style_context()
        style_context.add_class("submenu-button")
        style_context.add_class("power-profile")
        self.add(self._content_box)
        self.set_can_focus(True)
        setup_cursor_hover(self)
        self.set_active(active)

    def select(self):
        power_profile_service.active_profile = self.profile

    def set_active(self, active: str):
        if self.profile == active:
            self._content_box.add_style_class("active")
        else:
            self._content_box.remove_style_class("active")


class PowerProfileSubMenu(QuickSubMenu):
    """A submenu to display power profile options."""

    def __init__(self, **kwargs):
        self.profiles = [
            profile["Profile"] for profile in power_profile_service.profiles
        ]

        self.profile_items = None
        self.scan_button = None

        self.profile_box = ListBox(
            name="power-profile-container",
            visible=True,
            selection_mode="none",
            style_classes="power-profile-container",
        )

        super().__init__(
            title=_("widget.quick_settings.power_profiles.title"),
            title_icon=get_text_icon("powerprofiles.power-saver", "󰌪"),
            scan_button=self.scan_button,
            child=self.profile_box,
            **kwargs,
        )

        self._profile_changed_handler = power_profile_service.connect(
            "changed", self.on_profile_changed
        )
        self.profile_box.connect("row-activated", self._on_row_activated)
        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, *_):
        if self._profile_changed_handler is not None:
            from utils.functions import safe_disconnect

            safe_disconnect(power_profile_service, self._profile_changed_handler)
            self._profile_changed_handler = None

    def prepare_content(self):
        """Build the rows before expanding so the reveal animates to full height."""
        if self.profile_items is None:
            self.profile_items = [
                PowerProfileItem(
                    profile=profile, active=power_profile_service.active_profile
                )
                for profile in self.profiles
            ]

            for item in self.profile_items:
                add_list_row(self.profile_box, item)
        else:
            # Keep the items in sync with the current profile.
            self.on_profile_changed()

    def _on_row_activated(self, _listbox: ListBox, row: Gtk.ListBoxRow):
        if isinstance(row, PowerProfileItem):
            row.select()

    def on_profile_changed(self, *_):
        if self.profile_items is None:
            return
        active = power_profile_service.active_profile
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
            action_title=_("widget.quick_settings.power_profiles.title"),
            action_label=_("widget.quick_settings.power_profiles.saver"),
            submenu_factory=submenu_factory,
            **kwargs,
        )
        self.popup = popup

        self.update_action_button()
        self.set_active_style(True)
        self.action_button.set_sensitive(False)

        self._register_handlers(
            power_profile_service,
            {"changed": self.update_action_button},
        )

    def unslug(self, text: str) -> str:
        return " ".join([word.capitalize() for word in text.split("-")])

    def update_action_button(self, *_):
        active = power_profile_service.active_profile
        self.action_icon.set_label(icon_name_to_icon(active))
        self.set_action_label(self.unslug(active))

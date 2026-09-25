from fabric.utils import Gtk
from fabric.widgets.box import Box
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from services import audio_service
from shared.list import ListBox
from shared.submenu import QuickSubMenu, scrolled_list_content
from utils.i18n import _
from utils.icons import get_text_icon, symbolic_icons
from widgets.quick_settings.sliders.audio import AudioSlider


class AudioSubMenu(QuickSubMenu):
    """A submenu to display application-specific audio controls."""

    def __init__(self, **kwargs):
        self.client = audio_service

        # Create refresh button first since parent needs it
        self.scan_button = None

        # Create app list container
        self.app_list = ListBox(
            selection_mode="none",
            name="app-list",
            style_classes="menu",
        )

        # Sized to its content, so the sliders fit without a scrollbar until
        # there are many apps.
        self.child = scrolled_list_content(self.app_list, max_height=320)

        # Initialize parent with our components
        super().__init__(
            title=_("widget.quick_settings.audio.title"),
            title_icon=get_text_icon("volume.high", "󰕾"),
            scan_button=self.scan_button,
            child=Box(orientation="v", children=[self.child]),
            h_expand=True,
            **kwargs,
        )

        # Connect signals
        self.client.connect("changed", self.update_apps)
        self.update_apps()

    def update_apps(self, *args):
        """Update the list of applications with volume controls."""
        # Clear existing rows
        while row := self.app_list.get_row_at_index(0):
            self.app_list.remove(row)

        # Add applications
        for app in self.client.applications:
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("menu-item")

            # Main container
            box = Box(
                orientation="v",
                spacing=6,
                margin_start=6,
                margin_end=6,
                margin_top=3,
                margin_bottom=3,
            )

            # App name
            name_box = Box(orientation="h", spacing=12, h_expand=True)

            # App icon
            icon = Image(
                icon_name=app.icon_name or symbolic_icons["audio"]["volume"]["high"],
                icon_size=18,
            )
            name_box.pack_start(icon, False, True, 0)

            # App name label
            name_label = Label(
                label=app.name,
                style_classes="submenu-item-label",
                h_align="start",
                tooltip_text=app.description or app.name,
            )
            name_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            name_box.pack_start(name_label, True, True, 0)

            box.add(name_box)

            # Audio controls
            audio_box = Box(
                orientation="h",
                spacing=6,
                margin_start=24,  # Indent to align with app name
            )

            # Create audio slider for this app
            slider = AudioSlider(app)
            audio_box.pack_start(slider, True, True, 0)

            box.add(audio_box)

            row.add(box)
            self.app_list.add(row)

        self.app_list.show_all()

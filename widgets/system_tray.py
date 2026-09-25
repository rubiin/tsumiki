from fabric.system_tray.service import SystemTray as SystemTrayService
from fabric.system_tray.service import SystemTrayItem as SystemTrayItemService
from fabric.utils import (
    Gdk,
    GLib,
    Gtk,
    bulk_connect,
    logger,
)
from fabric.widgets.box import Box
from fabric.widgets.grid import Grid
from fabric.widgets.image import Image

from shared.buttons import HoverButton
from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget
from utils.functions import path_exists_ttl
from utils.icon_resolver import IconResolver
from utils.icons import get_text_icon, symbolic_icons
from utils.pixbuf import load_file_pixbuf
from utils.widget_utils import nerd_font_icon


class BaseSystemTray:
    """Base class for system tray implementations."""

    def on_button_click(self, button: ButtonWidget, item: SystemTrayItemService, event):
        if event.button in (1, 3):
            menu = item.get_property("menu")
            if menu:
                menu.popup_at_widget(
                    button,
                    Gdk.Gravity.SOUTH,
                    Gdk.Gravity.NORTH,
                    event,
                )
            else:
                item.context_menu(event.x, event.y)

    def resolve_icon(self, item: SystemTrayItemService, icon_size: int = 16):
        pixmap = item.icon_pixmap

        try:
            if pixmap is not None:
                return pixmap.as_pixbuf(icon_size, "bilinear")

            icon_name = item.icon_name

            # Some tray items expose no icon name; use stable fallback.
            if not icon_name:
                return self._load_default_theme_icon(icon_size)

            logger.info(
                f"""[SystemTray] Resolving icon: {icon_name}, size: {icon_size}"""
            )

            # Use custom theme path if available
            if item.icon_theme:
                try:
                    return item.icon_theme.load_icon(
                        icon_name,
                        icon_size,
                        Gtk.IconLookupFlags.FORCE_SIZE,
                    )
                except GLib.Error:
                    # Fallback to default theme if custom path fails
                    return self._load_default_theme_icon(icon_size, icon_name)

            # for some apps, the icon_name is a path
            if path_exists_ttl(icon_name, ttl=60):
                pixbuf = load_file_pixbuf(icon_name, icon_size, icon_size)
                if pixbuf is not None:
                    return pixbuf
            return self._load_default_theme_icon(icon_size, icon_name)
        except (GLib.Error, TypeError, ValueError):
            return self._load_default_theme_icon(icon_size)

    @staticmethod
    def _load_default_theme_icon(icon_size: int, icon_name: str | None = None):
        """Resolve an icon from the default theme, or the missing glyph."""
        resolver = IconResolver()
        return resolver.get_icon_theme_icon(
            icon_name or symbolic_icons["missing"], icon_size
        )

    def _bake_item_button(self, item: SystemTrayItemService) -> HoverButton:
        button = HoverButton(style_classes="flat")

        if self.config.get("tooltip", True) and self.tooltips_enabled:
            button.set_tooltip_text(item.get_property("title") or "")

        button.connect(
            "button-press-event",
            lambda button, event: self.on_button_click(button, item, event),
        )
        self._update_item_button(item, button)
        return button

    def _update_item_button(self, item: SystemTrayItemService, button: HoverButton):
        button.set_image(
            Image(pixbuf=self.resolve_icon(item=item, icon_size=self.icon_size))
        )


class SystemTrayMenu(Box, BaseSystemTray):
    """A widget to display additional system tray items in a grid."""

    def __init__(self, config: dict, parent_widget=None, **kwargs):
        super().__init__(
            name="system_tray-menu",
            orientation="vertical",
            style_classes="panel-menu",
            **kwargs,
        )

        self.config = config
        self.parent_widget = parent_widget

        self.icon_size = config.get("icon_size", 16)

        # Create a grid for the items
        self.grid = Grid(
            row_spacing=8,
            column_spacing=12,
            margin_top=6,
            margin_bottom=6,
            margin_start=12,
            margin_end=12,
        )
        self.add(self.grid)

        self.row = 0
        self.column = 0
        self.max_columns = 3

    def add_item(self, item):
        self.grid.attach(item, self.column, self.row, 1, 1)
        self.column += 1
        if self.column >= self.max_columns:
            self.column = 0
            self.row += 1

        # Update parent widget visibility if parent is available
        if self.parent_widget:
            self.parent_widget.update_visibility()

    def on_item_removed(self, button: ButtonWidget):
        """Handle when an item is removed from the menu."""
        button.destroy()
        # Update parent widget visibility if parent is available
        if self.parent_widget:
            self.parent_widget.update_visibility()


class SystemTrayWidget(ButtonWidget, PopoverMixin, BaseSystemTray):
    """A widget to display the system tray items."""

    def __init__(self, **kwargs):
        super().__init__(name="system_tray", **kwargs)

        # Create main tray box and toggle icon
        self.tray_box = Box(name="system_tray-box", orientation="horizontal", spacing=2)
        self._items: dict[str, HoverButton] = {}

        self.icon_size = self.config.get("icon_size", 16)
        self.hidden_list = self.config.get("hidden", [])

        self.chevron_icon = nerd_font_icon(
            icon=get_text_icon("chevron.down", ""),
            props={
                "style_classes": ["panel-font-icon", "chevron-icon"],
            },
        )

        # Set children directly in Box to avoid double styling
        self.container_box.add(self.tray_box)

        if self.not_empty(self.hidden_list):
            self.container_box.add(self.chevron_icon)
            self.create_menu()
            # Connect click handler
            self.connect("clicked", self.on_click)

        self.setup_popover(
            lambda: self.popup_menu,
            connect_clicked=False,
            on_close_callback=self._on_popover_closed,
        )

        self._watcher = SystemTrayService()

        bulk_connect(
            self._watcher,
            {
                "item-added": self.on_item_added,
                "item-removed": self.on_item_removed,
            },
        )

        # Load existing items
        for item_id in self._watcher.items:
            self.on_item_added(self._watcher, item_id)

        # Initial visibility check
        self.update_visibility()

    def create_menu(self):
        # Create popup menu for hidden items
        self.popup_menu = SystemTrayMenu(config=self.config, parent_widget=self)

    def _on_popover_closed(self, *_):
        self.remove_style_class("active")
        self.chevron_icon.set_label(get_text_icon("chevron.down", ""))

    # show or hide the popup menu
    def on_click(self, *_):
        visible = self._popup is not None and self._popup.get_visible()

        self.toggle_css_class("active", not visible)

        if visible:
            self.hide_popover()
            self.chevron_icon.set_label(get_text_icon("chevron.down", ""))
        else:
            self.show_popover()
            self.chevron_icon.set_label(get_text_icon("chevron.up", ""))

    def update_visibility(self):
        """Update widget visibility based on configuration and item count."""
        hide_when_empty = self.config.get("hide_when_empty", False)

        if not hide_when_empty:
            self.set_visible(True)
            return

        # Check if there are any visible items in the tray
        has_visible_items = self.not_empty(self.tray_box.get_children())
        # Check if there are items in the popup menu
        has_hidden_items = hasattr(self, "popup_menu") and self.not_empty(
            self.popup_menu.grid.get_children()
        )

        # Widget is visible if there are any items (visible or hidden)
        self.set_visible(has_visible_items or has_hidden_items)

    def not_empty(self, item):
        return len(item) > 0

    def on_item_removed(self, _, item_identifier):
        """Handle when an item is removed from the system tray."""
        item_button = self._items.get(item_identifier)

        if not item_button:
            return

        item_button.destroy()
        self._items.pop(item_identifier)
        # Update visibility after an item is removed
        self.update_visibility()
        return

    def on_item_added(self, _, item_identifier: str):

        item = self._watcher.items.get(item_identifier)
        if not item or item.id is None:
            return

        logger.info(f"[SystemTray] Item added: {item_identifier}")

        # Get item title for matching
        title = item.get_property("title") or ""

        # Check if item should be ignored completely
        ignored_list = self.config.get("ignored", [])

        if any(x.lower() in title.lower() for x in ignored_list):
            return

        # Check if item should be hidden in popover
        is_hidden = any(x.lower() in title.lower() for x in self.hidden_list)
        item_button = self._bake_item_button(item=item)
        self._items[item.identifier] = item_button

        # Add to appropriate container
        if is_hidden:
            self.popup_menu.add_item(item_button)
        else:
            self.tray_box.pack_start(item_button, False, False, 0)

        # Update visibility after adding an item
        self.update_visibility()

"""Wallpaper picker: a grid of thumbnails, per-monitor assignment.

Ported from muhchaudhary/fabric-nix's picker. Left click sets the wallpaper on
every monitor; right click (or Shift+Enter / Menu) picks a single monitor.
"""

import os
from collections.abc import Callable

from fabric.utils import Gdk, GLib, Gtk, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.scrolledwindow import ScrolledWindow

from shared.buttons import HoverButton
from shared.popup import PopupWindow
from shared.rounded_image import RoundedCoverImage
from utils.decorators import run_in_thread
from utils.functions import ensure_directory, spawn_detached
from utils.pixbuf import load_file_pixbuf
from utils.wallpaper import (
    THUMB_SIZE,
    apply_wallpaper,
    list_monitors_async,
    list_wallpapers,
    query_active_wallpapers,
    restore_wallpapers,
    save_wallpaper,
    thumbnail_path,
    wallpaper_directory,
    wallpaper_path,
    wallpaper_thumbs_directory,
)

TILE_WIDTH = 256
TILE_HEIGHT = 144  # 16:9
TILE_RADIUS = 10
GRID_COLUMNS = 3


def _display_path(path: str) -> str:
    return path.replace(GLib.get_home_dir(), "~")


def _build_thumbnail(source: str, target: str) -> bool:
    """Centre-crop *source* to the tile aspect ratio and write *target*."""
    try:
        from PIL import Image as PILImage
        from PIL import ImageOps

        with PILImage.open(source) as img:
            image = ImageOps.exif_transpose(img)
            image = ImageOps.fit(image, THUMB_SIZE, method=PILImage.Resampling.LANCZOS)
            image.save(target)
        return True
    except Exception as e:
        logger.exception(f"[Wallpaper] Failed to thumbnail {source}: {e}")
        return False


class WallpaperCard(HoverButton):
    """A wallpaper thumbnail, with chips naming the monitors showing it."""

    def __init__(
        self,
        wallpaper_name: str,
        on_set: Callable[[str, list[str] | None], None],
        get_monitors: Callable[[], list[dict]],
        **kwargs,
    ):
        self.wallpaper_name = wallpaper_name
        self.wp_path = wallpaper_path(wallpaper_name)
        self._on_set = on_set
        self._get_monitors = get_monitors
        self._monitors_using: list[str] = []
        self._menu: Gtk.Menu | None = None
        self.tile = RoundedCoverImage(TILE_WIDTH, TILE_HEIGHT, TILE_RADIUS)

        self.chips = Box(
            name="wallpaper-monitor-chips",
            spacing=4,
            h_align="end",
            v_align="start",
        )
        self.chips.set_no_show_all(True)

        super().__init__(
            name="wallpaper-card",
            tooltip_text=(
                f"{wallpaper_name} - click: all monitors, right-click: one monitor"
            ),
            child=Overlay(child=self.tile, overlays=self.chips),
            on_clicked=lambda *_: self._on_set(self.wp_path, None),
            on_button_press_event=self._on_button_press,
            **kwargs,
        )
        # keyboard focus belongs to the FlowBoxChild around the card
        self.set_can_focus(False)
        self._load_thumbnail()

    @property
    def monitors_using(self) -> list[str]:
        return self._monitors_using

    def set_monitors_using(self, monitor_names: list[str]):
        self._monitors_using = monitor_names
        for child in self.chips.get_children():
            child.destroy()
        for name in monitor_names:
            chip = Box(name="wallpaper-monitor-chip", children=Label(label=name))
            chip.show_all()
            self.chips.add(chip)
        self.chips.set_visible(bool(monitor_names))
        self.toggle_css_class("current", bool(monitor_names))

    def _on_button_press(self, _button, event):
        if event.button != 3:
            return False
        self.show_menu(event)
        return True

    def show_menu(self, event: Gdk.Event | None = None):
        """The monitor menu, at the pointer for a click, else under the card."""
        menu = Gtk.Menu()
        menu.get_style_context().add_class("wallpaper-monitor-menu")
        monitors = self._get_monitors()
        for monitor in monitors:
            name = monitor["name"]
            label = f"{name}  -  {monitor['width']}x{monitor['height']}"
            if name in self._monitors_using:
                label = "> " + label
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _i, n=name: self._on_set(self.wp_path, [n]))
            menu.append(item)
        if len(monitors) > 1:
            menu.append(Gtk.SeparatorMenuItem())
        all_item = Gtk.MenuItem(label="All monitors")
        all_item.connect("activate", lambda _i: self._on_set(self.wp_path, None))
        menu.append(all_item)
        menu.show_all()
        # keep a reference, or the menu is garbage collected while open
        self._menu = menu
        if event is not None:
            menu.popup_at_pointer(event)
        else:
            menu.popup_at_widget(
                self, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None
            )
            menu.select_first(False)

    def set_on_all_monitors(self):
        self._on_set(self.wp_path, None)

    def _set_thumbnail(self, thumb_file: str):
        pixbuf = load_file_pixbuf(thumb_file, THUMB_SIZE[0], THUMB_SIZE[1])
        if pixbuf:
            self.tile.set_pixbuf(pixbuf)

    def _load_thumbnail(self):
        thumb_file = thumbnail_path(self.wallpaper_name)
        if os.path.exists(thumb_file):
            self._set_thumbnail(thumb_file)
            return
        self._create_thumbnail(thumb_file)

    @run_in_thread
    def _create_thumbnail(self, thumb_file: str):
        ensure_directory(wallpaper_thumbs_directory(), sync=True)
        if _build_thumbnail(self.wp_path, thumb_file):
            GLib.idle_add(self._set_thumbnail, thumb_file)


class WallpaperGrid(ScrolledWindow):
    """The thumbnail grid. Populated on open, cleared on close to free pixbufs."""

    def __init__(
        self,
        on_wallpaper_set: Callable[[bool], None] | None = None,
        **kwargs,
    ):
        self._on_wallpaper_set = on_wallpaper_set or (lambda _all_monitors: None)
        self._built = False
        self._cards: dict[str, WallpaperCard] = {}
        self._monitors: list[dict] = []
        # move keyboard focus to the current wallpaper once hyprpaper says which it is
        self._focus_current = False

        self.flowbox = Gtk.FlowBox(
            homogeneous=True,
            selection_mode=Gtk.SelectionMode.NONE,
            min_children_per_line=GRID_COLUMNS,
            max_children_per_line=GRID_COLUMNS,
            row_spacing=6,
            column_spacing=6,
            valign=Gtk.Align.START,
        )
        self.flowbox.set_name("wallpaper-grid")
        self.flowbox.show()
        self.empty_label = Label(name="wallpaper-empty", visible=False)

        super().__init__(
            name="wallpaper-scroll",
            h_scrollbar_policy="never",
            min_content_size=(-1, 520),
            max_content_size=(-1, 520),
            child=Box(orientation="v", children=[self.flowbox, self.empty_label]),
            **kwargs,
        )

        self.flowbox.connect(
            "child-activated",
            lambda _box, child: self._card_of(child).set_on_all_monitors(),
        )
        self.flowbox.connect("key-press-event", self._on_key_press)
        self.flowbox.set_vadjustment(self.get_vadjustment())

    @staticmethod
    def _card_of(child: Gtk.FlowBoxChild) -> WallpaperCard:
        return child.get_child()

    def _on_key_press(self, _, event: Gdk.EventKey) -> bool:
        # Menu key, Shift+F10 or Shift+Enter: choose a monitor for it
        shift = event.state & Gdk.ModifierType.SHIFT_MASK
        if not (
            event.keyval == Gdk.KEY_Menu
            or (
                shift
                and event.keyval in (Gdk.KEY_F10, Gdk.KEY_Return, Gdk.KEY_KP_Enter)
            )
        ):
            return False
        focused = self.flowbox.get_focus_child()
        if isinstance(focused, Gtk.FlowBoxChild):
            self._card_of(focused).show_menu()
        return True

    def focus_card(self, card: WallpaperCard | None = None):
        """Give keyboard focus to *card* (or the first one) and scroll to it."""
        child = (
            card.get_parent()
            if card is not None
            else self.flowbox.get_child_at_index(0)
        )
        if isinstance(child, Gtk.FlowBoxChild):
            # child_focus rather than grab_focus: the FlowBox cursor moves with it
            child.child_focus(Gtk.DirectionType.TAB_FORWARD)

    def build(self) -> int:
        """Populate the grid (once until cleared); returns the image count."""
        if self._built:
            return len(self._cards)
        self._built = True

        names = list_wallpapers()
        for name in names:
            card = WallpaperCard(
                name,
                on_set=self._set_wallpaper,
                get_monitors=lambda: self._monitors,
            )
            self._cards[card.wp_path] = card
            self.flowbox.add(card)
        self.flowbox.show_all()
        folder = _display_path(wallpaper_directory())
        self.empty_label.set_label(f"No images in {folder}")
        self.empty_label.set_visible(not names)
        self.get_vadjustment().set_value(0)
        self.focus_card()
        self._focus_current = True
        self.refresh_assignments()
        return len(names)

    def refresh_assignments(self):
        """Ask hyprpaper what each monitor shows and update the chips."""

        def on_monitors(monitors: list[dict]):
            self._monitors = monitors

            def on_active(active: dict[str, str]):
                by_path: dict[str, list[str]] = {}
                # keep monitors in layout order (left to right)
                for monitor in sorted(self._monitors, key=lambda m: (m["x"], m["y"])):
                    path = active.get(monitor["name"])
                    if path:
                        by_path.setdefault(path, []).append(monitor["name"])
                for path, card in self._cards.items():
                    card.set_monitors_using(by_path.get(path, []))
                if self._focus_current:
                    self._focus_current = False
                    current = next(
                        (c for c in self._cards.values() if c.monitors_using), None
                    )
                    if current is not None:
                        self.focus_card(current)

            query_active_wallpapers(on_active)

        list_monitors_async(on_monitors)

    def _set_wallpaper(self, path: str, monitor_names: list[str] | None):
        targets = (
            [m["name"] for m in self._monitors]
            if monitor_names is None
            else monitor_names
        )
        save_wallpaper(path, monitor_names)
        apply_wallpaper(path, targets, on_done=self.refresh_assignments)
        self._on_wallpaper_set(monitor_names is None)

    def clear(self):
        for child in self.flowbox.get_children():
            child.destroy()
        self._cards.clear()
        self._built = False


class WallPaperPickerOverlay(PopupWindow):
    """The wallpaper picker popup."""

    def __init__(self):
        self.wallpaper_grid = WallpaperGrid(on_wallpaper_set=self._on_wallpaper_set)
        self.count_label = Label(name="wallpaper-picker-subtitle", h_align="start")
        open_folder_button = Button(
            name="wallpaper-picker-folder",
            tooltip_text="Open wallpaper folder",
            image=Image(icon_name="folder-open-symbolic", icon_size=16),
            v_align="center",
            on_clicked=self._open_folder,
        )
        header = CenterBox(
            name="wallpaper-picker-header",
            start_children=Box(
                orientation="v",
                children=[
                    Label("Wallpapers", name="wallpaper-picker-title", h_align="start"),
                    self.count_label,
                ],
            ),
            end_children=Box(spacing=12, children=[open_folder_button]),
        )
        super().__init__(
            layer="top",
            name="wallpaper-picker",
            child=Box(
                # distinct from the popup name: the click-catcher padding boxes
                # inherit the window name and must not get the panel styling
                name="wallpaper-picker-content",
                orientation="v",
                spacing=12,
                children=[header, self.wallpaper_grid],
            ),
            transition_duration=250,
            transition_type="crossfade",
            anchor="center",
            enable_inhibitor=True,
        )
        restore_wallpapers()

    def _on_wallpaper_set(self, all_monitors: bool):
        # setting a single monitor keeps the picker open for the next one
        if all_monitors:
            self._set_popup_visible(False)

    def _open_folder(self, *_):
        spawn_detached(["xdg-open", wallpaper_directory()])
        self._set_popup_visible(False)

    def _set_popup_visible(self, visible: bool):
        super()._set_popup_visible(visible)
        if visible:
            count = self.wallpaper_grid.build()
            folder = _display_path(wallpaper_directory())
            plural = "s" if count != 1 else ""
            self.count_label.set_label(
                f"{count} image{plural} - {folder} - right-click to pick a monitor"
            )
        else:
            self.wallpaper_grid.clear()

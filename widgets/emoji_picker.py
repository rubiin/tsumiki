from fabric.utils import Gdk, Gio, GLib, idle_add, logger, os, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack

from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget
from utils.constants import ASSETS_DIR
from utils.decorators import run_in_thread
from utils.functions import ensure_file, read_json_file
from utils.i18n import _
from utils.widget_utils import nerd_font_icon

# Module-level cache for emoji data — parsed once, reused across picker opens
_emoji_data_cache: dict | None = None


class EmojiPickerMenu(Box):
    """A widget to display an emoji picker."""

    def __init__(self, parent, **kwargs):
        super().__init__(
            name="emoji_picker-menu",
            **kwargs,
        )

        config = parent.config

        self._parent = parent

        self.selected_index = -1
        self._per_row = config.get("per_row", 5)
        self.emojis_per_page = self._per_row * config.get("per_column", 5)
        self.current_page_index = 0
        self.filtered_emojis = []
        self.total_pages = 0

        self._arranger_handler: int = 0
        self._all_emojis = None  # Lazy loaded
        self._emoji_loading = False  # Loading state flag
        self._pending_query = None  # Query to execute after loading
        self._emoji_file_path = f"{ASSETS_DIR}/emoji.json"
        ensure_file(os.path.dirname(self._emoji_file_path))

        self.stack = Stack(
            name="viewport",
            spacing=4,
            orientation="v",
            transition_type="slide-up-down",
            transition_duration=200,
        )
        self.search_entry = Entry(
            name="search-entry",
            placeholder="Search Emojis...",
            h_expand=True,
            notify_text=lambda entry, *_: self.arrange_viewport(entry.get_text()),
            on_activate=lambda entry, *_: self.on_search_entry_activate(
                entry.get_text()
            ),
            on_key_press_event=self.on_search_entry_key_press,
        )
        self.search_entry.props.xalign = 0.5

        self.picker_box = Box(
            name="picker-box",
            spacing=10,
            h_expand=True,
            orientation="v",
            children=[
                self.search_entry,
                self.stack,
            ],
        )

        self.resize_viewport()

        self.add(self.picker_box)

    def _load_emoji_data_async(self, callback=None):
        """Load emoji data in background thread."""
        global _emoji_data_cache

        if self._emoji_loading:
            return

        # Use module-level cache if available (persists across picker opens)
        if _emoji_data_cache is not None:
            self._all_emojis = _emoji_data_cache
            if callback:
                callback()
            return

        if self._all_emojis is not None:
            if callback:
                callback()
            return

        self._emoji_loading = True

        @run_in_thread
        def _load():
            try:
                data = read_json_file(self._emoji_file_path)
                emoji_dict = data if isinstance(data, dict) else {}
                idle_add(self._on_emoji_load_complete, emoji_dict, callback)
            except Exception as e:
                logger.exception(f"Error loading emoji data: {e}")
                idle_add(self._on_emoji_load_complete, {}, callback)

        _load()

    def _on_emoji_load_complete(self, emoji_dict, callback):
        """Called on main thread when emoji loading completes."""
        global _emoji_data_cache

        self._all_emojis = emoji_dict
        _emoji_data_cache = emoji_dict  # Cache at module level for next picker open
        self._emoji_loading = False

        # Execute pending query if any
        if self._pending_query is not None:
            query = self._pending_query
            self._pending_query = None
            self._do_arrange_viewport(query)
        elif callback:
            callback()

        return False

    def close_picker(self):
        self.selected_index = -1
        self.search_entry.set_text("")
        self.current_page_index = 0
        self._parent.popup.hide_popover()

    def arrange_viewport(self, query: str = ""):
        """Arrange viewport - loads emoji data async if needed."""
        if self._all_emojis is None:
            # Show loading indicator and load in background
            self._pending_query = query
            self._show_loading()
            self._load_emoji_data_async()
            return

        self._do_arrange_viewport(query)

    def _show_loading(self):
        """Show a loading indicator while emoji data loads."""
        self.stack.children = []
        loading_box = Box(
            name="loading-box",
            orientation="v",
            h_align="center",
            v_align="center",
            children=[
                Label(
                    label=_("widget.emoji_picker.loading"), style_classes="dim-label"
                ),
            ],
        )
        self.stack.add(loading_box)

    def _do_arrange_viewport(self, query: str = ""):
        remove_handler(self._arranger_handler) if self._arranger_handler else None
        self.stack.children = []
        self.selected_index = -1
        self.current_page_index = 0

        self.filtered_emojis = [
            (emoji_char, emoji_info)
            for emoji_char, emoji_info in self._all_emojis.items()
            if query.casefold()
            in (
                emoji_info.get("name", "") + " " + emoji_info.get("group", "")
            ).casefold()
        ]
        self.total_pages = (
            (len(self.filtered_emojis) + self.emojis_per_page - 1)
            // self.emojis_per_page
            if self.filtered_emojis
            else 0
        )

        self._page_cache: dict[int, Box] = {}
        # Build only the first page eagerly; remaining pages are built lazily
        # on navigation. Rebuilding ~60 button trees on every keystroke caused
        # heavy style/layout churn while typing in the search box.
        if self.total_pages > 0:
            self._build_page(0)
        # Show first page
        if self.total_pages > 0:
            self.stack.set_visible_child_name("page-0")

        should_resize = not query

        if should_resize:
            self.resize_viewport()
        if query.strip() != "" and self._get_all_emoji_buttons():
            self.update_selection(0)

    def _build_page(self, page_index: int) -> Box:
        """Build a single page of emoji buttons and cache it."""
        start_index = page_index * self.emojis_per_page
        end_index = min(
            (page_index + 1) * self.emojis_per_page, len(self.filtered_emojis)
        )
        page_emojis = self.filtered_emojis[start_index:end_index]

        page_box = Box(name=f"page-box-{page_index}", orientation="v", spacing=4)
        grid_box = Box(name="emoji-grid-box", orientation="v", spacing=2)

        row_box = None
        for i, (emoji_char, emoji_info) in enumerate(page_emojis):
            if i % self._per_row == 0:
                row_box = Box(name="emoji-row-box", orientation="h", spacing=2)
                grid_box.add(row_box)
            if row_box is not None:
                row_box.add(self._bake_emoji_slot(emoji_char, emoji_info))
        page_box.add(grid_box)
        self.stack.add_named(page_box, f"page-{page_index}")
        self._page_cache[page_index] = page_box
        return page_box

    def _load_page(self, page_index: int):
        self.update_selection(-1)
        # Use cached page if available, otherwise build it
        if page_index not in self._page_cache:
            self._build_page(page_index)
        self.stack.set_visible_child_name(f"page-{page_index}")

        buttons = self._get_all_emoji_buttons()
        if buttons and self.selected_index != -1:
            page_relative_index = self.selected_index % self.emojis_per_page
            if page_relative_index < len(buttons):
                self.update_selection(page_relative_index)
            else:
                self.update_selection(len(buttons) - 1)

    def resize_viewport(self):
        return False

    def _bake_emoji_slot(self, emoji_char: str, emoji_info: dict, **kwargs) -> Button:
        # Label can be child directly - no need for wrapper Box
        button = Button(
            name="emoji-slot-button",
            child=Label(
                name="emoji-char-label",
                label=emoji_char,
                use_markup=True,
                v_align="center",
                h_align="center",
                css_name="emoji-char-label",
            ),
            tooltip_text=emoji_info.get("name", "Unknown"),
            on_clicked=lambda *_: (
                self._copy_emoji_to_clipboard(emoji_char),
                self.close_picker(),
            ),
            **kwargs,
        )
        return button

    def update_selection(self, new_index: int):
        buttons = self._get_all_emoji_buttons()
        if not buttons:
            self.selected_index = -1
            return

        if self.selected_index != -1 and self.selected_index < len(buttons):
            current_button = buttons[self.selected_index]
            current_button.get_style_context().remove_class("selected")
            if not buttons or current_button not in buttons:
                self.selected_index = -1

        if 0 <= new_index < len(buttons):
            new_button = buttons[new_index]
            new_button.get_style_context().add_class("selected")
            self.selected_index = new_index
        else:
            self.selected_index = -1

    def _get_all_emoji_buttons(self):
        buttons = []
        current_page = self.stack.get_visible_child()
        if (
            current_page
            and current_page.get_children()
            and current_page.get_children()[0].get_children()
        ):
            for row_box in current_page.get_children()[0].get_children():
                buttons.extend(row_box.get_children())
        return buttons

    def on_search_entry_activate(self, text):
        buttons = self._get_all_emoji_buttons()
        if buttons:
            if self.selected_index != -1:
                buttons[self.selected_index].clicked()
            elif buttons and text.strip() != "":
                buttons[0].clicked()

    def on_search_entry_key_press(self, widget, event):
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right):
            self._move_selection_2d(event.keyval)
            return True
        elif event.keyval == Gdk.KEY_Escape:
            self.close_picker()
            return True
        return False

    def _move_selection_2d(self, keyval):
        buttons = self._get_all_emoji_buttons()
        total_items_current_page = len(buttons)
        if total_items_current_page == 0:
            return

        rows = 3
        columns = 9

        if self.selected_index == -1:
            if keyval in (Gdk.KEY_Down, Gdk.KEY_Right):
                new_index = 0
            elif keyval in (Gdk.KEY_Up, Gdk.KEY_Left):
                new_index = total_items_current_page - 1
            else:
                return
        else:
            current_index_page = self.selected_index
            row = current_index_page // columns
            col = current_index_page % columns

            if keyval == Gdk.KEY_Right:
                new_col = (col + 1) % columns
                new_row = row
                if new_col == 0:
                    new_row = row + 1
            elif keyval == Gdk.KEY_Left:
                new_col = (col - 1) % columns
                new_row = row
                if new_col == (columns - 1):
                    new_row = row - 1
            elif keyval == Gdk.KEY_Down:
                new_row = row + 1
                new_col = col
            elif keyval == Gdk.KEY_Up:
                new_row = row - 1
                new_col = col
            else:
                return

            if new_row >= rows:
                if self.current_page_index < self.total_pages - 1:
                    current_col = col  # Keep track of current column
                    self.current_page_index += 1
                    self._load_page(self.current_page_index)
                    new_index = current_col  # Try to keep the same column
                    if (
                        new_index >= total_items_current_page
                    ):  # if column is out of bound, select last
                        new_index = total_items_current_page - 1
                    self.selected_index = -1
                    self.update_selection(new_index)
                    return
                else:
                    new_index = total_items_current_page - 1
            elif new_row < 0:
                if self.current_page_index > 0:
                    current_col = col  # Keep track of current column
                    self.current_page_index -= 1
                    self._load_page(self.current_page_index)
                    new_index = (
                        rows - 1
                    ) * columns + current_col  # Select last row, same column
                    if (
                        new_index >= total_items_current_page
                    ):  # if column is out of bound, select last
                        new_index = total_items_current_page - 1
                    self.selected_index = -1
                    self.update_selection(new_index)
                    return
                else:
                    new_index = 0
            else:
                new_index = new_row * columns + new_col
                if new_index >= total_items_current_page:
                    new_index = total_items_current_page - 1

        if new_index < 0:
            new_index = 0
        elif new_index >= total_items_current_page:
            new_index = total_items_current_page - 1

        self.update_selection(new_index)

    def _copy_emoji_to_clipboard(self, emoji_char: str):
        """Copy emoji to clipboard asynchronously."""
        try:
            launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDIN_PIPE)
            proc = launcher.spawnv(["wl-copy"])
            proc.communicate_async(
                GLib.Bytes.new(emoji_char.encode("utf-8")),
                None,
                lambda p, r, _: None,  # Fire and forget
                None,
            )
        except (GLib.Error, OSError) as e:
            logger.exception(f"Clipboard copy failed: {e}")


class EmojiPickerWidget(ButtonWidget, PopoverMixin):
    """A widget to display and manage emoji picker."""

    def __init__(self, **kwargs):
        super().__init__(name="emoji_picker", **kwargs)

        self.container_box.add(
            nerd_font_icon(
                icon=self.config.get("icon"),
                props={"style_classes": ["panel-font-icon"]},
            )
        )

        if self.config.get("label", True):
            self.container_box.add(
                Label(label=_("widget.emoji_picker.label"), style_classes="panel-text")
            )

        self.set_tooltip_if_enabled(_("widget.emoji_picker.tooltip"))

        self.setup_popover(lambda: EmojiPickerMenu(parent=self))

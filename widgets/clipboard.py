import shutil
import tempfile
from typing import ClassVar
from urllib.parse import unquote, urlparse

from fabric.utils import (
    Gdk,
    GdkPixbuf,
    Gio,
    GLib,
    Gtk,
    bulk_connect,
    idle_add,
    logger,
    os,
    re,
    remove_handler,
    time,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

from shared.list import ListBox, near_list_end, next_batch_size
from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget, TeardownMixin
from utils.i18n import _
from utils.widget_utils import get_text_icon, nerd_font_icon


class ClipHistoryMenu(Box, TeardownMixin):
    """A widget to display and manage clipboard history."""

    _html_img_re = None

    def _get_html_img_re(self):
        if self._html_img_re is None:
            self.__class__._html_img_re = re.compile(r"^\s*<img\s+")
        return self._html_img_re

    def __init__(
        self,
        parent=None,
        config=None,
        **kwargs,
    ):
        super().__init__(
            name="clipboard-menu",
            orientation="v",
            spacing=10,
            h_expand=True,
            **kwargs,
        )

        self._parent = parent

        # Create a temporary directory for image icons
        self.tmp_dir = tempfile.mkdtemp(prefix="cliphist-")
        self.image_cache = {}  # Cache for image previews (limited to MAX_IMAGE_CACHE)
        self.MAX_IMAGE_CACHE = 10  # Limit cache size to prevent memory bloat

        self.selected_index = -1  # Track the selected item index
        self._arranger_handler = 0
        self.clipboard_items = []
        self.filtered_items = []
        self._loading = False
        self._pending_updates = False
        self.show_images = config.get("show_images", False)
        self.item_tooltip = config.get("item_tooltip", False)
        self.enable_pinning = config.get("enable_pinning", True)

        if self._parent is not None and not hasattr(
            self._parent, "pinned_clipboard_ids"
        ):
            self._parent.pinned_clipboard_ids = set()
        self.pinned_item_ids = (
            self._parent.pinned_clipboard_ids if self._parent is not None else set()
        )

        # Pagination state, reset for new scan
        self.items_loaded = 0
        self.batch_size = 10
        self.loading = False
        self.max_items = 0  # Will be set when items are loaded

        self._cache_loaded_at: float | None = (
            None  # Timestamp of last clipboard list load
        )
        self._search_timer_id = None  # Timer ID for search text change
        self._item_widgets: dict[str, Button] = {}  # Cache of item_id -> button widget

        self.viewport = ListBox(
            name="viewport",
            v_align="fill",
            h_align="fill",
            h_expand=True,
            v_expand=True,
        )

        self.search_entry = Entry(
            name="search-entry",
            placeholder="search history",
            h_expand=True,
            primary_icon_name="system-search",
            secondary_icon_name="edit-clear",
            on_activate=self.use_selected_item,
            on_key_press_event=self.on_search_entry_key_press,
        )

        bulk_connect(
            self.search_entry,
            {
                "notify::text": self.on_search_text_changed,
                "icon-press": self.on_icon_press,
            },
        )

        self.search_entry.props.xalign = 0.1

        self.scrolled_window = ScrolledWindow(
            name="scrolled-window",
            spacing=10,
            min_content_size=(300, 200),
            max_content_size=(300, 200),
            child=self.viewport,
        )
        self.vadj = self.scrolled_window.get_vadjustment()
        self.vadj.connect("value-changed", self.on_scroll)

        self.header_box = Box(
            name="header_box",
            spacing=10,
            orientation="h",
            children=[
                self.search_entry,
                Button(
                    name="sync-button",
                    label=get_text_icon("ui.refresh", ""),
                    tooltip_text=_("widget.clipboard.sync"),
                    on_clicked=self._load_clipboard_items_async,
                ),
                Button(
                    name="clear-button",
                    label=get_text_icon("trash.empty", ""),
                    tooltip_text=_("widget.clipboard.clear"),
                    on_clicked=self.clear_history,
                ),
            ],
        )

        self.children = [self.header_box, self.scrolled_window]
        self.connect("destroy", self._on_destroy)
        self._search_timer_id = None

    def on_icon_press(self, entry, icon_pos, event):
        if icon_pos == Gtk.EntryIconPosition.SECONDARY:
            self.search_entry.set_text("")

    _launcher_cache: ClassVar[dict[int, Gio.SubprocessLauncher]] = {}

    def _make_launcher(self, flags):
        """Return a cached ``Gio.SubprocessLauncher`` for the given flags."""
        if flags not in self._launcher_cache:
            self._launcher_cache[flags] = Gio.SubprocessLauncher.new(flags)
        return self._launcher_cache[flags]

    def _load_next_batch(self):
        if self.loading or self.max_items == 0 or self.items_loaded >= self.max_items:
            return
        self.loading = True

        items_to_add = next_batch_size(
            self.items_loaded, self.max_items, self.batch_size
        )

        for i in range(self.items_loaded, self.items_loaded + items_to_add):
            self.viewport.add(self.create_clipboard_item(self.filtered_items[i]))

        self.items_loaded += items_to_add
        self.loading = False

        # Force GTK to recalculate sizes, then check if viewport needs more items
        self.viewport.queue_resize()
        GLib.idle_add(self._fill_viewport)

        if self.search_entry.get_text() and self.viewport.get_children():
            self.update_selection(0)

    def _fill_viewport(self):
        """Load more items if the viewport still has room."""
        if self.loading or self.max_items == 0 or self.items_loaded >= self.max_items:
            return False

        vadj = self.scrolled_window.get_vadjustment()
        # If content fits without scrolling, load more to fill the viewport
        if vadj.get_upper() <= vadj.get_page_size():
            self._load_next_batch()
        return False

    def on_scroll(self, adjustment: Gtk.Adjustment):
        """Load next page when user scrolls near the bottom."""
        if self.loading or self.max_items == 0 or self.items_loaded >= self.max_items:
            return

        # This list prefetches earlier than the others: its rows are tall.
        if near_list_end(adjustment, threshold=100):
            self._load_next_batch()

    def on_search_text_changed(self, entry, pspec):
        # Remove any existing pending filter operation
        if self._search_timer_id is not None:
            self._unregister_repeater(self._search_timer_id)
            GLib.source_remove(self._search_timer_id)
            self._search_timer_id = None

        # Start a new timer to filter after a delay, registered for auto-cleanup
        self._search_timer_id = self._register_repeater(
            GLib.timeout_add(
                250,  # Milliseconds delay
                lambda: self._perform_filter_after_delay(entry),
            )
        )

    def _perform_filter_after_delay(self, entry):
        self.filter_items(entry, None)  # Call the actual filter method
        self._search_timer_id = None  # Reset the timer ID
        return False  # Do not repeat the timeout

    def close(self, *_):
        """Close the clipboard history panel"""
        self.viewport.remove_all()
        self.selected_index = -1  # Reset selection
        self.filtered_items = []
        if self._parent is not None:
            self._parent.hide_popover()

    def open(self):
        """Open the clipboard history panel and load items"""
        if self._loading:
            return

        self._loading = True
        self.search_entry.set_text("")
        self.search_entry.grab_focus()
        self._load_clipboard_items_async()

    def _load_clipboard_items_async(self, *_):
        """Load clipboard items asynchronously without blocking UI"""
        try:
            # Use Gio.Subprocess for true async execution
            launcher = self._make_launcher(
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
            )
            proc = launcher.spawnv(["cliphist", "list"])
            proc.communicate_async(None, None, self._on_clipboard_list_ready, None)
        except (GLib.Error, OSError) as e:
            logger.exception(f"Error starting cliphist: {e}")
            self._loading = False

    def _on_clipboard_list_ready(self, proc, result, user_data):
        """Callback when clipboard list command completes"""
        try:
            _, stdout, _ = proc.communicate_finish(result)
            if stdout:
                stdout_str = stdout.get_data().decode("utf-8", errors="replace")
                lines = stdout_str.strip().split("\n")
                new_items = []
                for line in lines:
                    if not line or "<meta http-equiv" in line:
                        continue
                    new_items.append(line)
                self._update_items(new_items)
        except (GLib.Error, UnicodeDecodeError, ValueError) as e:
            logger.exception(f"Error loading clipboard history: {e}")
        finally:
            self._loading = False
            if self._pending_updates:
                self._pending_updates = False
                self._load_clipboard_items_async()

    def _update_items(self, new_items):
        """Update the items list from main thread"""
        self.clipboard_items = new_items
        self._cache_loaded_at = time.time()
        available_ids = {
            item.split("\t", 1)[0] if "\t" in item else item for item in new_items
        }
        self.pinned_item_ids.intersection_update(available_ids)
        self._display_clipboard_items()

    def _display_clipboard_items(self, filter_text=""):
        """Display clipboard items in the viewport"""
        remove_handler(self._arranger_handler) if self._arranger_handler else None
        self.viewport.remove_all()
        self._item_widgets.clear()
        self.selected_index = -1  # Reset selection

        # Reset scroll to top
        self.vadj.set_value(0)

        # Filter items if search text is provided
        needle = filter_text.lower()
        filtered_items = [
            item
            for item in self.clipboard_items
            if needle in (item.split("\t", 1)[1] if "\t" in item else item).lower()
        ]

        if self.enable_pinning:
            filtered_items.sort(
                key=lambda line: (
                    0 if line.split("\t", 1)[0] in self.pinned_item_ids else 1
                )
            )

        self.filtered_items = filtered_items
        self.viewport.v_align = "start"  # Align to top when showing items
        # Show message if no items are found
        if not filtered_items:
            self.filtered_items = []
            # Create a container box to better center the message
            container = Box(
                name="no-clip-container",
                orientation="v",
                h_align="center",
                v_align="center",
                h_expand=True,
                spacing=10,
                v_expand=True,
            )

            # Show a message if no clipboard items
            label = Label(
                name="no-clip",
                label=_("widget.clipboard.empty"),
                h_align="center",
                v_align="center",
            )
            image = Image(
                name="no-clip-icon",
                icon_name="clipboard-symbolic",
                icon_size=32,
                h_align="center",
                v_align="center",
            )

            container.add(image)
            container.add(label)
            self.viewport.v_align = "center"
            self.viewport.add(container)
            return

        # Pagination: start with first page, then append on scroll.
        self.max_items = len(filtered_items)
        self.items_loaded = 0
        self.loading = False
        self._load_next_batch()

    def create_clipboard_item(self, item):
        """Create a button for a clipboard item"""
        # Extract ID and content
        parts = item.split("\t", 1)
        item_id = parts[0] if len(parts) > 1 else "0"
        content = parts[1] if len(parts) > 1 else item
        is_pinned = item_id in self.pinned_item_ids

        # Truncate content for display
        display_text = content.strip()
        if len(display_text) > 100:
            display_text = display_text[:97] + "..."

        # Check if this is an image by examining the content
        is_image = self.is_image_data(content)

        is_file_image = self.is_file_image(content) and os.path.exists(
            unquote(urlparse(content).path)
        )

        if is_image and self.show_images:
            # For images, create item with image preview
            button = Button(
                name="slot-button",
                child=Box(
                    name="slot-box",
                    orientation="h",
                    spacing=10,
                    children=[
                        Image(name="clip-icon", h_align="start"),  # Placeholder
                        Label(
                            name="clip-label",
                            label=self._format_item_label("[Image]", is_pinned),
                            ellipsization="end",
                            v_align="center",
                            h_align="start",
                            h_expand=True,
                        ),
                    ],
                ),
                tooltip_text=(
                    self._format_item_tooltip("Image in clipboard", is_pinned)
                    if self.item_tooltip
                    else None
                ),
                on_clicked=lambda *_, id=item_id: self.paste_item(id),
            )
            # Load image preview in background
            self._load_image_preview_async(item_id, button)

        elif is_file_image:
            button = Button(
                name="slot-button",
                child=Box(
                    name="slot-box",
                    orientation="h",
                    spacing=10,
                    children=[
                        Image(
                            name="clip-icon",
                            h_align="start",
                            image_file=unquote(urlparse(content).path),
                            size=72,
                        ),  # Placeholder
                        Label(
                            name="clip-label",
                            label=self._format_item_label("[File]", is_pinned),
                            ellipsization="end",
                            v_align="center",
                            h_align="start",
                            h_expand=True,
                        ),
                    ],
                ),
                tooltip_text=(
                    self._format_item_tooltip("File in clipboard", is_pinned)
                    if self.item_tooltip
                    else None
                ),
                on_clicked=lambda *_, id=item_id: self.paste_item(id),
            )
        else:
            # For text, create regular item
            button = self.create_text_item_button(
                item_id,
                display_text,
                item_tooltip=self.item_tooltip,
                is_pinned=is_pinned,
            )

        # Add key press event handler for Enter key

        bulk_connect(
            button,
            {
                "key-press-event": lambda widget, event, id=item_id: (
                    self.on_item_key_press(widget, event, id)
                ),
                "button-press-event": lambda widget, event, id=item_id: (
                    self.on_item_key_press(widget, event, id)
                ),
            },
        )

        # Make sure button can receive focus and key events
        button.set_can_focus(True)
        button.add_events(Gdk.EventMask.KEY_PRESS_MASK)

        # Cache the button for future reuse
        self._item_widgets[item_id] = button

        return button

    def _rebuild_viewport_from_cache(self):
        """Rebuild the viewport reusing cached item widgets (avoids full rebuild)."""
        children = list(self.viewport.get_children())

        # Detach all children from viewport without destroying them
        for child in children:
            self.viewport.remove(child)

        # Rebuild from cache in sorted order
        # Use items_loaded to preserve scroll position and loaded state
        visible_count = min(self.items_loaded, len(self.filtered_items))
        for i in range(visible_count):
            item = self.filtered_items[i]
            item_id = item.split("\t", 1)[0]

            if item_id in self._item_widgets:
                button = self._item_widgets[item_id]
                # Update the button to reflect current pin state
                self._refresh_button_pin_state(button, item_id, item)
                self.viewport.add(button)
            else:
                button = self.create_clipboard_item(item)
                self.viewport.add(button)

        # Keep items_loaded unchanged - don't reset to batch_size
        self.max_items = len(self.filtered_items)

        # Restore selection
        if self.selected_index >= 0 and self.selected_index < len(
            self.viewport.get_children()
        ):
            new_button = self.viewport.get_children()[self.selected_index]
            new_button.get_style_context().add_class("selected")

    def _refresh_button_pin_state(self, button, item_id, item):
        """Update a cached button's label/tooltip when pin state changes."""
        is_pinned = item_id in self.pinned_item_ids
        parts = item.split("\t", 1)
        content = parts[1] if len(parts) > 1 else item

        display_text = content.strip()
        if len(display_text) > 100:
            display_text = display_text[:97] + "..."

        # Find the label child and update it
        child = button.get_child()
        if isinstance(child, Box):
            for sub in child.get_children():
                if isinstance(sub, Label):
                    sub.set_label(self._format_item_label(display_text, is_pinned))
                    break
        elif isinstance(child, Label):
            child.set_label(self._format_item_label(display_text, is_pinned))

        if self.item_tooltip:
            button.set_tooltip_text(self._format_item_tooltip(display_text, is_pinned))

    def _load_image_preview_async(self, item_id, button):
        """Load image preview asynchronously"""
        if item_id in self.image_cache:
            # Use cached pixbuf
            idle_add(self._update_image_button, button, self.image_cache[item_id])
            return

        try:
            launcher = self._make_launcher(
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
            )
            proc = launcher.spawnv(["cliphist", "decode", item_id])
            proc.communicate_async(None, None, self._on_image_loaded, (item_id, button))
        except (GLib.Error, OSError) as e:
            logger.exception(f"Error starting image decode: {e}")

    def _on_image_loaded(self, proc, result, user_data):
        """Callback when image decode completes"""
        item_id, button = user_data
        try:
            _, stdout, _ = proc.communicate_finish(result)
            if stdout:
                loader = GdkPixbuf.PixbufLoader()
                loader.write(stdout.get_data())
                loader.close()
                pixbuf = loader.get_pixbuf()
                width, height = pixbuf.get_width(), pixbuf.get_height()
                max_size = 72
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))
                pixbuf = pixbuf.scale_simple(
                    new_width, new_height, GdkPixbuf.InterpType.BILINEAR
                )
                # Limit cache size to prevent memory bloat
                if len(self.image_cache) >= self.MAX_IMAGE_CACHE:
                    # Remove oldest entry (first key)
                    oldest_key = next(iter(self.image_cache))
                    del self.image_cache[oldest_key]
                self.image_cache[item_id] = pixbuf
                self._update_image_button(button, pixbuf)
        except (GLib.Error, ValueError, OSError) as e:
            logger.exception(f"Error loading image preview: {e}")

    def _update_image_button(self, button, pixbuf):
        """Update the button with the loaded image preview"""
        box = button.get_child()
        if box and len(box.get_children()) > 0:
            image_widget = box.get_children()[0]
            if isinstance(image_widget, Image):
                image_widget.set_from_pixbuf(pixbuf)

    def create_text_item_button(
        self, item_id, display_text, item_tooltip=False, is_pinned=False
    ):
        """Create a button for a text clipboard item"""
        return Button(
            name="slot-button",
            child=Label(
                name="clip-label",
                label=self._format_item_label(display_text, is_pinned),
                ellipsization="end",
                v_align="center",
                h_align="start",
                h_expand=True,
            ),
            tooltip_text=(
                self._format_item_tooltip(display_text, is_pinned)
                if item_tooltip
                else None
            ),
            on_clicked=lambda *_: self.paste_item(item_id),
        )

    def _format_item_label(self, label_text, is_pinned):
        if self.enable_pinning and is_pinned:
            return "📌 " + label_text
        return label_text

    def _format_item_tooltip(self, tooltip_text, is_pinned):
        if self.enable_pinning and is_pinned:
            return "Pinned - " + tooltip_text
        return tooltip_text

    def is_file_image(self, content):
        # Check for common image data patterns
        return content.startswith("file:///") and content.endswith(
            (".png", ".jpg", ".jpeg", ".bmp", ".gif")
        )

    def is_image_data(self, content):
        """Determine if clipboard content is likely an image"""

        return (
            content.startswith("data:image/")
            or content.startswith("\x89PNG")
            or content.startswith("GIF8")
            or content.startswith("\xff\xd8\xff")  # JPEG
            or self._get_html_img_re().match(content) is not None  # HTML image tag
            or (
                "binary" in content.lower()
                and any(
                    ext in content.lower()
                    for ext in ["jpg", "jpeg", "png", "bmp", "gif"]
                )
            )
        )

    def paste_item(self, item_id):
        """Copy the selected item to the clipboard asynchronously"""
        try:
            launcher = self._make_launcher(
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
            )
            proc = launcher.spawnv(["cliphist", "decode", item_id])
            proc.communicate_async(None, None, self._on_paste_decoded, None)
        except (GLib.Error, OSError) as e:
            logger.exception(f"Error starting paste decode: {e}")

    def _on_paste_decoded(self, proc, result, user_data):
        """Callback when paste decode completes"""
        try:
            _, stdout, _ = proc.communicate_finish(result)
            if stdout:
                # Now pipe to wl-copy
                launcher = self._make_launcher(Gio.SubprocessFlags.STDIN_PIPE)
                wl_proc = launcher.spawnv(["wl-copy"])
                wl_proc.communicate_async(
                    GLib.Bytes.new(stdout.get_data()),
                    None,
                    self._on_paste_complete,
                    None,
                )
        except (GLib.Error, UnicodeDecodeError, ValueError) as e:
            logger.exception(f"Error decoding paste item: {e}")

    def _on_paste_complete(self, proc, result, user_data):
        """Callback when wl-copy completes"""
        try:
            proc.communicate_finish(result)
            self.close()
        except (GLib.Error, OSError) as e:
            logger.exception(f"Error pasting clipboard item: {e}")

    def delete_item(self, item_id):
        """Delete the selected clipboard item asynchronously"""
        if item_id in self.pinned_item_ids:
            self.pinned_item_ids.discard(item_id)
        try:
            launcher = self._make_launcher(Gio.SubprocessFlags.NONE)
            proc = launcher.spawnv(["cliphist", "delete", item_id])
            proc.wait_async(None, self._on_delete_complete, None)
        except (GLib.Error, OSError) as e:
            logger.exception(f"Error starting delete: {e}")

    def _on_delete_complete(self, proc, result, user_data):
        """Callback when delete completes"""
        try:
            proc.wait_finish(result)
            self._pending_updates = True
            if not self._loading:
                self._load_clipboard_items_async()
        except (GLib.Error, OSError) as e:
            logger.exception(f"Error deleting clipboard item: {e}")

    def clear_history(self, *_):
        """Clear all clipboard history asynchronously"""
        try:
            launcher = self._make_launcher(Gio.SubprocessFlags.NONE)
            proc = launcher.spawnv(["cliphist", "wipe"])
            proc.wait_async(None, self._on_clear_complete, None)
        except (GLib.Error, OSError) as e:
            logger.exception(f"Error starting clear: {e}")

    def _on_clear_complete(self, proc, result, user_data):
        """Callback when clear completes"""
        try:
            proc.wait_finish(result)
            self.pinned_item_ids.clear()
            self._pending_updates = True
            if not self._loading:
                self._load_clipboard_items_async()
        except (GLib.Error, OSError) as e:
            logger.exception(f"Error clearing clipboard history: {e}")

    def filter_items(self, entry, *_):
        """Filter clipboard items based on search text"""
        self._display_clipboard_items(entry.get_text())

    def on_search_entry_key_press(self, widget, event):
        """Handle key presses in the search entry"""
        if event.keyval == Gdk.KEY_Down:
            self.move_selection(1)
            return True
        elif event.keyval == Gdk.KEY_Up:
            self.move_selection(-1)
            return True
        elif event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.use_selected_item()
            return True
        elif event.keyval == Gdk.KEY_Home:
            self.update_selection(0)
            return True
        elif event.keyval == Gdk.KEY_End:
            children = self.viewport.get_children()
            if children:
                self.update_selection(len(children) - 1)
            return True
        elif event.keyval == Gdk.KEY_Delete:
            self.delete_selected_item()
            return True
        elif event.keyval in (Gdk.KEY_p, Gdk.KEY_P) and self.enable_pinning:
            self.toggle_selected_pin()
            return True
        elif event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def toggle_selected_pin(self):
        """Toggle pin for currently selected clipboard item."""
        item_id = self._get_selected_item_id()
        if item_id is None:
            return
        self.toggle_pin_item(item_id)

    def toggle_pin_item(self, item_id):
        """Pin or unpin item, then refresh current list."""
        if not self.enable_pinning:
            return

        if item_id in self.pinned_item_ids:
            self.pinned_item_ids.remove(item_id)
        else:
            self.pinned_item_ids.add(item_id)

        # Re-sort filtered_items (pinned float to top)
        needle = self.search_entry.get_text().lower()
        filtered_items = [
            item
            for item in self.clipboard_items
            if needle in (item.split("\t", 1)[1] if "\t" in item else item).lower()
        ]
        filtered_items.sort(
            key=lambda line: 0 if line.split("\t", 1)[0] in self.pinned_item_ids else 1
        )
        self.filtered_items = filtered_items

        # Rebuild using cached widgets instead of full destroy+create
        self._rebuild_viewport_from_cache()

    def update_selection(self, new_index):
        """Update the selected item in the viewport"""
        children = self.viewport.get_children()

        # Unselect current
        if self.selected_index != -1 and self.selected_index < len(children):
            current_button = children[self.selected_index]
            current_button.get_style_context().remove_class("selected")

        # Select new
        if new_index != -1 and new_index < len(children):
            new_button = children[new_index]
            new_button.get_style_context().add_class("selected")
            self.selected_index = new_index
            self.scroll_to_selected(new_button)
        else:
            self.selected_index = -1

    def move_selection(self, delta):
        """Move the selection up or down"""
        children = self.viewport.get_children()
        if not children:
            return

        # Allow starting selection from nothing
        if self.selected_index == -1:
            new_index = 0 if delta > 0 else len(children) - 1
        else:
            new_index = self.selected_index + delta

        new_index = max(0, min(new_index, len(children) - 1))
        self.update_selection(new_index)

    def _scroll(self, button):
        adj = self.scrolled_window.get_vadjustment()
        alloc = button.get_allocation()
        if alloc.height == 0:
            return False  # Retry if allocation isn't ready

        y = alloc.y
        height = alloc.height
        page_size = adj.get_page_size()
        current_value = adj.get_value()

        # Calculate visible boundaries
        visible_top = current_value
        visible_bottom = current_value + page_size

        if y < visible_top:
            # Item above viewport - align to top
            adj.set_value(y)
        elif y + height > visible_bottom:
            # Item below viewport - align to bottom
            new_value = y + height - page_size
            adj.set_value(new_value)
        return False

    def scroll_to_selected(self, button):
        """Scroll to ensure the selected item is visible"""

        idle_add(self._scroll, button)

    def use_selected_item(self, *_):
        """Use (paste) the selected clipboard item"""
        item_id = self._get_selected_item_id()
        if item_id is not None:
            self.paste_item(item_id)

    def delete_selected_item(self):
        """Delete the selected clipboard item"""
        item_id = self._get_selected_item_id()
        if item_id is not None:
            self.delete_item(item_id)

    def _get_selected_item_id(self):
        """Resolve the currently selected clipboard item id."""
        if not self.filtered_items:
            return None

        if self.selected_index == -1:
            self.update_selection(0)

        if self.selected_index == -1 or self.selected_index >= len(self.filtered_items):
            return None

        # Get the item ID from the first part before the tab
        item_line = self.filtered_items[self.selected_index]
        return item_line.split("\t", 1)[0]

    def on_item_key_press(self, widget, event, item_id):
        """Handle key press events on clipboard items"""
        if event.type == Gdk.EventType.BUTTON_PRESS:
            if self.enable_pinning and getattr(event, "button", 0) == 3:
                self.toggle_pin_item(item_id)
                return True
            # Copy item to clipboard and close
            self.paste_item(item_id)
            return True

        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            # Copy item to clipboard and close
            self.paste_item(item_id)
            return True
        if event.keyval in (Gdk.KEY_p, Gdk.KEY_P) and self.enable_pinning:
            self.toggle_pin_item(item_id)
            return True
        return False

    def _cleanup_resources(self):
        """Best-effort cleanup for timers, caches, and temporary resources."""
        self._search_timer_id = None

        if self._arranger_handler:
            remove_handler(self._arranger_handler)
            self._arranger_handler = 0

        self.viewport.remove_all()
        self.clipboard_items.clear()
        self.image_cache.clear()

        if hasattr(self, "tmp_dir") and self.tmp_dir and os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            self.tmp_dir = ""

    def _on_destroy(self, *_):
        self._cleanup_resources()

    def __del__(self):
        """Clean up temporary files on destruction"""
        try:
            self._cleanup_resources()
        except Exception as e:
            logger.exception(f"Error cleaning up temporary files: {e}")


class ClipBoardWidget(ButtonWidget, PopoverMixin):
    """A widget to display and manage clipboard history."""

    def __init__(self, **kwargs):
        super().__init__(name="clipboard", **kwargs)

        self.container_box.add(
            nerd_font_icon(
                icon=self.config.get("icon"),
                props={"style_classes": ["panel-font-icon"]},
            )
        )

        if self.config.get("label", True):
            self.container_box.add(Label(label="Clip", style_classes="panel-text"))

        self.set_tooltip_if_enabled(_("widget.clipboard.tooltip"))

        self.setup_popover(self._build_popover)

    def _build_popover(self):
        return ClipHistoryMenu(parent=self, config=self.config)

    def show_popover(self, *_):
        super().show_popover()
        if self.popup:
            self.popup.content._loading = False
            self.popup.content.open()

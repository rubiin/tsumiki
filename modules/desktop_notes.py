"""Sticky notes on the desktop: right-click the desktop to add one, drag it by
its top strip, type straight into it. Saved per monitor between restarts.
"""

import warnings
from collections.abc import Callable

from fabric.utils import Gdk, Gtk
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label

from services import note_service
from services.desktop_notes import NotesService
from shared.widget_container import BaseWindow, tooltips_enabled
from utils.constants import NOTE_COLORS
from utils.icons import get_text_icon
from utils.widget_settings import BarConfig

NOTE_HEIGHT = 180


def _monitor_name(window: Gtk.Window | None = None) -> str:
    """The GDK plug name for the monitor this desktop sits on."""
    display = Gdk.Display.get_default()
    if display is None:
        return "default"

    screen = display.get_default_screen()
    if screen is None:
        return "default"

    index: int | None = None
    gdk_window = window.get_window() if window is not None else None
    if gdk_window is not None:
        monitor_index = screen.get_monitor_at_window(gdk_window)
        if monitor_index >= 0:
            index = monitor_index

    if index is None:
        index = max(0, screen.get_primary_monitor())

    with warnings.catch_warnings():
        # Deprecated, but GTK3 has no other way to get connector names.
        warnings.simplefilter("ignore", DeprecationWarning)
        name = screen.get_monitor_plug_name(index)
    return name or str(index)


class NoteWidget(Box):
    """One note: add on the left, move/lock/colour/close on the right, text below."""

    def __init__(
        self,
        note: dict,
        store: NotesService,
        note_width: int,
        on_move: Callable[["NoteWidget", int, int], None],
        on_delete: Callable[["NoteWidget"], None],
        on_add: Callable[["NoteWidget"], None],
        on_hint: Callable[[str | None, Gtk.Widget | None], None],
        tooltips: bool = True,
    ):
        self.note = note
        self.store = store
        self.tooltips = tooltips
        self._on_hint = on_hint
        self._drag_from: tuple[float, float, int, int] | None = None
        self._locked = bool(note.get("locked", False))

        def watch(widget: Gtk.Widget, text: Callable[[], str]) -> None:
            if not self.tooltips:
                return
            widget.connect(
                "enter-notify-event", lambda *_: self._on_hint(text(), widget)
            )
            widget.connect("leave-notify-event", lambda *_: self._on_hint(None, None))

        add = Button(
            name="note-add",
            child=Label(name="note-add-icon", label=get_text_icon("ui.plus")),
            on_clicked=lambda *_: on_add(self),
        )
        # The drag strip doubles as the spacer that pushes the controls right.
        self.handle = EventBox(
            name="note-handle",
            h_expand=True,
            events=["button-press", "button-release", "pointer-motion"],
            child=Label(
                name="note-grip",
                label=get_text_icon("ui.drag"),
                h_align="end",
                v_align="center",
            ),
        )
        self.handle.connect("button-press-event", self._on_press)
        self.handle.connect("button-release-event", self._on_release)
        self.handle.connect("motion-notify-event", self._on_motion)
        self.lock_button = Button(
            name="note-lock",
            child=Label(name="note-lock-icon", label=get_text_icon("ui.unlock")),
            on_clicked=lambda *_: self._toggle_lock(),
        )
        color_dot = Button(
            name="note-color",
            on_clicked=lambda *_: self._cycle_color(),
        )
        delete = Button(
            name="note-delete",
            child=Label(
                name="note-delete-icon", label=get_text_icon("ui.window_close")
            ),
            on_clicked=lambda *_: on_delete(self),
        )

        self.text_view = Gtk.TextView()
        self.text_view.set_name("note-text")
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_size_request(note_width, NOTE_HEIGHT)
        buffer = self.text_view.get_buffer()
        buffer.set_text(note.get("text", ""))
        buffer.connect("changed", self._on_text_changed)

        super().__init__(
            name="desktop-note",
            orientation="v",
            children=[
                Box(
                    name="note-bar",
                    children=[add, self.handle, self.lock_button, color_dot, delete],
                ),
                self.text_view,
            ],
        )
        self._on_move = on_move
        self._apply_color()
        self._apply_lock()

        watch(add, lambda: "New note")
        watch(
            self.handle,
            lambda: "Note is locked" if self._locked else "Drag to move",
        )
        watch(
            self.lock_button,
            lambda: "Unlock note" if self._locked else "Lock note",
        )
        watch(color_dot, lambda: "Change colour")
        watch(delete, lambda: "Delete note")

    def _apply_lock(self) -> None:
        self.note["locked"] = self._locked
        icon = self.lock_button.get_child()
        if icon is not None:
            icon.set_label(
                get_text_icon("ui.lock") if self._locked else get_text_icon("ui.unlock")
            )
        if self._locked:
            self.handle.add_style_class("locked")
        else:
            self.handle.remove_style_class("locked")

    def _toggle_lock(self) -> None:
        self._locked = not self._locked
        self._apply_lock()
        self.store.save_soon()

    def _apply_color(self) -> None:
        for color in NOTE_COLORS:
            self.remove_style_class(f"note-{color}")
        self.add_style_class(f"note-{self.note.get('color', NOTE_COLORS[0])}")

    def _cycle_color(self) -> None:
        current = self.note.get("color", NOTE_COLORS[0])
        index = NOTE_COLORS.index(current) if current in NOTE_COLORS else -1
        self.note["color"] = NOTE_COLORS[(index + 1) % len(NOTE_COLORS)]
        self._apply_color()
        self.store.save_soon()

    def _on_text_changed(self, buffer: Gtk.TextBuffer) -> None:
        start, end = buffer.get_bounds()
        self.note["text"] = buffer.get_text(start, end, False)
        self.store.save_soon()

    def _on_press(self, _widget, event: Gdk.EventButton) -> bool:
        self._on_hint(None, None)
        if event.button != 1 or self._locked:
            return False
        self._drag_from = (event.x_root, event.y_root, self.note["x"], self.note["y"])
        return True

    def _on_motion(self, _widget, event: Gdk.EventMotion) -> bool:
        if self._drag_from is None:
            return False
        start_x, start_y, note_x, note_y = self._drag_from
        self._on_move(
            self,
            max(0, round(note_x + event.x_root - start_x)),
            max(0, round(note_y + event.y_root - start_y)),
        )
        return True

    def _on_release(self, *_widget) -> bool:
        if self._drag_from is not None:
            self._drag_from = None
            self.store.save_soon()
        return False


def place(widget: Gtk.Widget, x: int, y: int) -> None:
    """Position an overlay child by its top-left corner."""
    widget.set_halign(Gtk.Align.START)
    widget.set_valign(Gtk.Align.START)
    widget.set_margin_start(max(0, x))
    widget.set_margin_top(max(0, y))


class NotesLayer:
    """This monitor's notes, each its own overlay child on the desktop."""

    def __init__(
        self,
        store: NotesService,
        monitor: str,
        overlay: Gtk.Overlay,
        note_width: int,
        tooltips: bool = True,
    ):
        self.store = store
        self.monitor = monitor
        self.overlay = overlay
        self.note_width = note_width
        self.tooltips = tooltips
        self.widgets: list[NoteWidget] = []
        self._visible = True
        # GTK's own tooltips need a popup surface, which a layer-shell window
        # cannot host on Wayland, so hints are drawn inside this overlay.
        self.hint = Label(name="note-hint", visible=False)
        self.hint.set_no_show_all(True)
        overlay.add_overlay(self.hint)
        overlay.set_overlay_pass_through(self.hint, True)
        for note in store.for_monitor(monitor):
            self._add_widget(note)

    def _add_widget(self, note: dict) -> NoteWidget:
        widget = NoteWidget(
            note,
            self.store,
            self.note_width,
            self._move,
            self._delete,
            self._add_from,
            self.show_hint,
            self.tooltips,
        )
        place(widget, note["x"], note["y"])
        self.overlay.add_overlay(widget)
        widget.show_all()
        widget.set_visible(self._visible)
        self.widgets.append(widget)
        return widget

    def set_visible(self, visible: bool) -> None:
        self._visible = visible
        for widget in self.widgets:
            widget.set_visible(visible)
        if not visible:
            self.hide_hint()

    def show_hint(self, text: str | None, widget: Gtk.Widget | None) -> None:
        """Draw a hint above the hovered control, inside the note window."""
        if not text or widget is None:
            self.hide_hint()
            return

        x, y = widget.translate_coordinates(self.overlay, 0, 0)
        self.hint.set_text(text)
        self.hint.set_halign(Gtk.Align.START)
        self.hint.set_valign(Gtk.Align.START)
        self.hint.set_margin_start(max(0, x - 2))
        self.hint.set_margin_top(y - 26 if y >= 28 else y + 28)
        self.hint.set_visible(True)
        self.overlay.reorder_overlay(self.hint, -1)

    def hide_hint(self) -> None:
        self.hint.set_visible(False)

    def add_note(self, x: int, y: int) -> None:
        widget = self._add_widget(self.store.add(self.monitor, x, y))
        widget.text_view.grab_focus()

    def _add_from(self, widget: NoteWidget) -> None:
        """Spawn a new note beside an existing one, like the reference note app."""
        self.add_note(widget.note["x"] + 24, widget.note["y"] + 24)

    def _move(self, widget: NoteWidget, x: int, y: int) -> None:
        widget.note["x"], widget.note["y"] = x, y
        place(widget, x, y)

    def _delete(self, widget: NoteWidget) -> None:
        self.store.remove(widget.note["id"])
        self.widgets.remove(widget)
        widget.destroy()


class DesktopNotes(BaseWindow):
    """A full-screen, click-through-free bottom layer holding the notes."""

    def __init__(self, config: BarConfig, **kwargs):
        self.config = config.get("modules", {}).get("desktop_notes", {})
        note_width = int(self.config.get("note_width", 240))
        self.tooltips = bool(self.config.get("tooltip", True)) and tooltips_enabled()
        self.store = note_service
        self.store.save_delay_ms = int(self.config.get("save_delay", 800))

        # The bare desktop catches right-clicks; each note is its own overlay
        # child, so clicks on a note reach the note instead of the background.
        self.background = EventBox(
            name="desktop-notes-background",
            events=["button-press"],
            h_expand=True,
            v_expand=True,
            child=Box(h_expand=True, v_expand=True),
        )
        self.background.connect("button-press-event", self._on_background_press)
        self.overlay = Gtk.Overlay()
        self.overlay.add(self.background)

        super().__init__(
            name="desktop_notes",
            layer=self.config.get("layer", "bottom"),
            anchor="top bottom left right",
            keyboard_mode="on-demand",
            child=self.overlay,
            **kwargs,
        )
        # Resolve the monitor only once layer-shell has placed the window.
        self.monitor_name = _monitor_name(self)
        self.notes = NotesLayer(
            self.store, self.monitor_name, self.overlay, note_width, self.tooltips
        )
        self.overlay.show_all()
        self.connect("destroy", lambda *_: self.store.flush())

    def _on_background_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button != 3:
            return False
        self.show_menu(event)
        return True

    def show_menu(self, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()
        coords = (max(0, round(event.x)), max(0, round(event.y)))

        new_note = Gtk.MenuItem(label="New note")
        new_note.connect("activate", lambda *_: self.notes.add_note(*coords))
        menu.append(new_note)

        menu.show_all()
        # Wayland places popups relative to a parent.
        menu.attach_to_widget(self.background, None)
        # Keep a reference, or the menu is garbage collected while open.
        self._menu = menu
        menu.popup_at_pointer(event)

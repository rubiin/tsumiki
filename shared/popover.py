import contextlib
from typing import ClassVar

from fabric import Signal
from fabric.utils import Gdk, GLib, GObject, bulk_connect, logger
from fabric.widgets.box import Box
from fabric.widgets.revealer import Revealer
from fabric.widgets.widget import Widget
from gi.repository import GtkLayerShell

from shared.widget_container import BaseWindow
from utils.functions import safe_disconnect
from utils.hyprland import hyprland_service

POPOVER_BAR_GAP = -70


class PopoverManager:
    """Singleton manager to handle shared resources for popovers."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        # Lazy-initialized overlay window
        self._overlay = None
        self._hyprland_connection = None

        # Keep track of active popovers
        self.active_popover = None
        self.available_windows = []

    @property
    def overlay(self):
        """Lazily create the overlay window on first access."""
        if self._overlay is None:
            self._overlay = BaseWindow(
                name="popover-overlay",
                style_classes="popover-overlay",
                title="tsumiki-popup",
                anchor="left top right bottom",
                margin="-50px 0px 0px 0px",
                exclusivity="auto",
                layer="overlay",
                type="top-level",
                visible=False,
                all_visible=False,
            )

            # Add empty box so GTK doesn't complain
            self._overlay.add(Box())

            # Close popover when clicking overlay
            self._overlay.connect("button-press-event", self.on_overlay_clicked)

            # Connect hyprland monitor change handler
            self._hyprland_connection = hyprland_service.connection
            self._hyprland_connection.connect(
                "event::focusedmonv2", self.on_monitor_change
            )

        return self._overlay

    def on_monitor_change(self, *_):
        if self.active_popover:
            self.active_popover.hide_popover()
        return True

    def on_overlay_clicked(self, *_):
        if self.active_popover:
            self.active_popover.hide_popover()
        return True

    def get_popover_window(self):
        """Get an available popover window or create a new one."""
        if self.available_windows:
            return self.available_windows.pop()

        window = BaseWindow(
            type="popup",
            layer="overlay",
            name="popover-window",
            anchor="left top",
            visible=False,
            all_visible=False,
        )
        GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.ON_DEMAND)
        window.set_keep_above(True)
        return window

    def return_popover_window(self, window):
        """Return a popover window to the pool."""
        # Remove any children
        for child in window.get_children():
            window.remove(child)

        window.hide()
        # Only keep a reasonable number of windows in the pool
        if len(self.available_windows) < 5:
            self.available_windows.append(window)
        else:
            # Let the window be garbage collected
            window.destroy()

    def activate_popover(self, popover):
        """Set the active popover and show overlay."""
        if self.active_popover and self.active_popover != popover:
            self.active_popover.hide_popover()

        self.active_popover = popover
        self.overlay.show()

    def clear_active_popover(self, popover):
        """Clear active popover only if it matches the current one."""
        if self.active_popover == popover:
            self.active_popover = None
            self.overlay.hide()


@Signal(
    name="popover-opened",
    flags=GObject.SignalFlags.RUN_LAST,
    rtype=GObject.TYPE_NONE,
    arg_types=(),
)
def popover_opened(widget: Widget): ...


@Signal(
    name="popover-closed",
    flags=GObject.SignalFlags.RUN_LAST,
    rtype=GObject.TYPE_NONE,
    arg_types=(),
)
def popover_closed(widget: Widget): ...


@GObject.type_register
class Popover(Widget):
    """Memory-efficient popover implementation."""

    __gsignals__: ClassVar = {
        "popover-opened": (GObject.SignalFlags.RUN_LAST, GObject.TYPE_NONE, ()),
        "popover-closed": (GObject.SignalFlags.RUN_LAST, GObject.TYPE_NONE, ()),
    }

    def __init__(
        self,
        point_to,
        content_factory=None,
        content=None,
        enable_boundary_checking=True,
        transition_type: str | None = None,
        transition_duration: int = 250,
    ):
        super().__init__()

        self._content_factory = content_factory
        self._point_to = point_to
        self._content_window = None
        self._content = content
        self._content_box = None
        self._enable_boundary_checking = enable_boundary_checking
        self._visible = False
        self._draw_handler_id = None
        self._focus_out_timeout_id = None
        self._revealer = None
        # None derives the slide direction from the edge the popover opens from.
        self._transition_type = transition_type
        self._transition_duration = transition_duration

        self._manager = PopoverManager()

    def set_content_factory(self, content_factory):
        """Set the content factory for the popover."""
        self._content_factory = content_factory

    def set_content(self, content):
        """Set the content for the popover."""
        self._content = content

    @property
    def content(self):
        """Return the content widget for the popover."""
        return self._content

    def set_pointing_to(self, widget):
        """Set the widget to point the popover at."""
        self._point_to = widget

    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape and self._manager.active_popover:
            self._manager.active_popover.hide_popover()
            return True
        return False

    def open(self, *_):
        if not self._content_window:
            try:
                created = self._create_popover()
            except Exception as e:
                logger.exception(f"Could not create popover! Error: {e}")
                return

            if not created:
                return
        else:
            self._manager.activate_popover(self)
            self.set_position()
            self._content_window.show()
            if self._revealer is not None:
                self._revealer.set_reveal_child(True)
            self._visible = True

        self.emit("popover-opened")

    def _get_widget_monitor_coordinates(self):
        allocation = self._point_to.get_allocation()
        window = self._point_to.get_window()

        relative_x = allocation.x
        relative_y = allocation.y

        toplevel = self._point_to.get_toplevel()
        with contextlib.suppress(Exception):
            translated = self._point_to.translate_coordinates(toplevel, 0, 0)
            if translated is not None:
                relative_x, relative_y = translated

        origin_x = 0
        origin_y = 0
        if toplevel is not None:
            with contextlib.suppress(Exception):
                origin = toplevel.get_window().get_origin()
                if isinstance(origin, tuple):
                    if len(origin) == 3:
                        _, origin_x, origin_y = origin
                    elif len(origin) == 2:
                        origin_x, origin_y = origin

        display = Gdk.Display.get_default()
        screen = display.get_default()
        monitor_at_window = screen.get_monitor_at_window(window)
        monitor_geometry = monitor_at_window.get_geometry()

        layer_x = None
        layer_y = None
        if toplevel is not None:
            with contextlib.suppress(Exception):
                if GtkLayerShell.is_layer_window(toplevel):
                    toplevel_allocation = toplevel.get_allocation()
                    anchored_left = GtkLayerShell.get_anchor(
                        toplevel, GtkLayerShell.Edge.LEFT
                    )
                    anchored_right = GtkLayerShell.get_anchor(
                        toplevel, GtkLayerShell.Edge.RIGHT
                    )
                    anchored_top = GtkLayerShell.get_anchor(
                        toplevel, GtkLayerShell.Edge.TOP
                    )
                    anchored_bottom = GtkLayerShell.get_anchor(
                        toplevel, GtkLayerShell.Edge.BOTTOM
                    )

                    if anchored_left and anchored_right:
                        layer_x = relative_x

                    if anchored_bottom and not anchored_top:
                        layer_y = (
                            monitor_geometry.height
                            - toplevel_allocation.height
                            + relative_y
                        )
                    elif anchored_top and not anchored_bottom:
                        layer_y = relative_y

        widget_x = layer_x
        if widget_x is None:
            widget_x = origin_x + relative_x - monitor_geometry.x

        widget_y = layer_y
        if widget_y is None:
            widget_y = origin_y + relative_y - monitor_geometry.y

        return widget_x, widget_y, allocation, monitor_geometry

    def _calculate_margins(self):
        widget_x, widget_y, widget_allocation, monitor_geometry = (
            self._get_widget_monitor_coordinates()
        )
        # The window tracks the reveal animation (1px tall while collapsed),
        # so measure the content requisition instead of the live window size.
        _, natural = self._content_box.get_preferred_size()
        popover_width, popover_height = natural.width, natural.height

        x = widget_x + (widget_allocation.width / 2) - (popover_width / 2)
        y = widget_y + widget_allocation.height + POPOVER_BAR_GAP

        opens_upward = widget_y >= monitor_geometry.height / 2
        if opens_upward:
            y = widget_y - popover_height + POPOVER_BAR_GAP * 0.2

        if self._enable_boundary_checking:
            if x <= 0:
                x = widget_x
            elif x + popover_width >= monitor_geometry.width:
                x = widget_x - popover_width + widget_allocation.width

            if y <= 0:
                y = 0
            elif y + popover_height >= monitor_geometry.height:
                y = max(monitor_geometry.height - popover_height, 0)

        if opens_upward:
            # Bottom-anchored: margin is the distance below the popover.
            bottom = monitor_geometry.height - y - popover_height
            return [0, 0, int(bottom), int(x)], True
        return [int(y), 0, 0, int(x)], False

    def set_position(self, position: tuple[int, int, int, int] | None = None):
        if position is None:
            margins, opens_upward = self._calculate_margins()
            # Anchor the edge the popover grows from, with a matching slide
            # direction, so the content unrolls out of the bar (Ax-Shell style).
            self._content_window.anchor = "left bottom" if opens_upward else "left top"
            if self._transition_type is None and self._revealer is not None:
                self._revealer.transition_type = (
                    "slide-up" if opens_upward else "slide-down"
                )
            self._content_window.set_margin(margins)
            return False

        self._content_window.set_margin(position)
        return False

    def on_content_ready(self, widget, event):
        if self._draw_handler_id is not None:
            safe_disconnect(self._content, self._draw_handler_id)
            self._draw_handler_id = None
        self.set_position()

    def _resolve_content(self) -> bool:
        """Ensure content is available, creating via factory if needed."""
        if self._content is None and self._content_factory is not None:
            self._content = self._content_factory()
        if self._content is None:
            logger.warning(
                "Could not create popover content: no content or content factory"
            )
            return False
        return True

    def _wire_popover_handlers(self):
        """Connect draw + focus/key handlers to the content window."""
        # Hack to fix wrong positioning for widgets not rendered immediately
        self._draw_handler_id = self._content.connect("draw", self.on_content_ready)
        bulk_connect(
            self._content_window,
            {
                "focus-out-event": self.on_popover_focus_out,
                "key-press-event": self.on_key_press,
            },
        )

    def _activate_popover(self):
        """Register with manager, position, show window, mark visible."""
        self._manager.activate_popover(self)
        self.set_position()
        self._content_window.show()
        if self._revealer is not None:
            self._revealer.set_reveal_child(True)
        self._visible = True

    def _create_popover(self):
        if not self._resolve_content():
            return False

        self._content_window = self._manager.get_popover_window()
        self._content_box = Box(name="popover-content", children=self._content)
        self._revealer = Revealer(
            name="popover-revealer",
            child=self._content_box,
            transition_type=self._transition_type or "slide-down",
            transition_duration=self._transition_duration,
        )
        self._revealer.set_size_request(-1, 1)
        self._content_window.add(self._revealer)
        self._wire_popover_handlers()
        self._activate_popover()
        return True

    def on_popover_focus_out(self, widget, event):
        # This helps with keyboard focus issues
        if self._focus_out_timeout_id is not None:
            GLib.source_remove(self._focus_out_timeout_id)
        self._focus_out_timeout_id = GLib.timeout_add(200, self._hide_after_focus_out)
        return False

    def _hide_after_focus_out(self):
        self._focus_out_timeout_id = None
        return self.hide_popover()

    def hide_popover(self):
        if not self._visible or not self._content_window:
            return False

        if self._focus_out_timeout_id is not None:
            GLib.source_remove(self._focus_out_timeout_id)
            self._focus_out_timeout_id = None

        self._visible = False

        if self._revealer is not None:
            self._revealer.set_reveal_child(False)
            GLib.timeout_add(self._transition_duration, self._finish_hide)
        else:
            self._finish_hide()

        return False

    def _finish_hide(self):
        if self._visible:
            return False
        self._content_window.hide()
        self._manager.clear_active_popover(self)
        self.emit("popover-closed")
        return False

    def hide(self, *_):
        """Compatibility helper for code paths that expect Gtk-like hide()."""
        return self.hide_popover()

    def get_visible(self):
        """Compatibility helper for mixins that query visibility."""
        return self._visible

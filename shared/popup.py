from typing import Literal

from fabric.utils import Gdk, GLib
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.widget import Widget

from shared.widget_container import BaseWindow
from utils.monitors import HyprlandWithMonitors
from utils.types import Anchor, Keyboard_Mode, Layer


class Padding(EventBox):
    """A widget to add padding around the child widget."""

    def __init__(self, name: str | None = None, style: str = "", **kwargs):
        super().__init__(
            name=name,
            h_expand=True,
            v_expand=True,
            child=Box(style=style, h_expand=True, v_expand=True),
            events=["button-press"],
            **kwargs,
        )
        self.set_can_focus(False)


class PopupRevealer(EventBox):
    """A widget to reveal a popup window."""

    def __init__(
        self,
        popup_window: "PopupWindow",
        decorations: str = "padding: 1px;",
        name: str | None = None,
        child: Widget | None = None,
        transition_type: Literal[
            "none",
            "crossfade",
            "slide-right",
            "slide-left",
            "slide-up",
            "slide-down",
        ] = "slide-down",
        transition_duration: int = 400,
    ):
        self.revealer: Revealer = Revealer(
            name=name,
            child=child,
            transition_type=transition_type,
            transition_duration=transition_duration,
            notify_child_revealed=lambda revealer, _: (
                [
                    revealer.hide(),
                    popup_window.set_visible(False),
                ]
                if not revealer.fully_revealed
                else None
            ),
            notify_reveal_child=lambda revealer, _: (
                [
                    popup_window.set_visible(True),
                ]
                if revealer.child_revealed
                else None
            ),
        )
        super().__init__(
            style=decorations,
            child=self.revealer,
        )


# anchor name -> (vertical position, horizontal alignment, inner h_expand)
_ANCHOR_LAYOUT: dict[str, tuple[str, str, bool | None]] = {
    "center-left": ("center", "left", None),
    "center": ("center", "center", None),
    "center-right": ("center", "right", None),
    "top": ("top", "center", None),
    "top-right": ("top", "right", False),
    "top-center": ("top", "center", False),
    "top-left": ("top", "left", False),
    "bottom-left": ("bottom", "left", False),
    "bottom-center": ("bottom", "center", False),
    "bottom-right": ("bottom", "right", True),
}


def _make_v_column(
    v_pos: str, name: str, popup: "PopupRevealer", h_expand: bool | None, **pad_kwargs
) -> Box:
    def pad():
        return Padding(name=name, **pad_kwargs)

    if v_pos == "top":
        children = [popup, pad()]
    elif v_pos == "bottom":
        children = [pad(), popup]
    else:
        children = [pad(), popup, pad()]
    kw: dict = {"orientation": "vertical", "children": children}
    if h_expand is not None:
        kw["h_expand"] = h_expand
    return Box(**kw)


def make_layout(anchor: str, name: str, popup: "PopupRevealer", **kwargs) -> Box:
    spec = _ANCHOR_LAYOUT.get(anchor)
    if spec is None:
        return make_layout(anchor="top-right", name=name, popup=popup, **kwargs)

    v_pos, h_align, inner_h_expand = spec

    def pad():
        return Padding(name=name, **kwargs)

    inner = _make_v_column(v_pos, name, popup, inner_h_expand, **kwargs)

    if h_align == "left":
        h_children = [inner, pad()]
    elif h_align == "right":
        h_children = [pad(), inner]
    else:
        h_children = [pad(), inner, pad()]

    return Box(children=h_children)


class PopupWindow(BaseWindow):
    """A popup window to display a message."""

    def __init__(
        self,
        layer: Layer = "overlay",
        name="popup-window",
        title="tsumiki",
        decorations="padding: 1px;",
        child: Widget | None = None,
        transition_type: Literal[
            "none",
            "crossfade",
            "slide-right",
            "slide-left",
            "slide-up",
            "slide-down",
        ]
        | None = None,
        transition_duration=100,
        popup_visible: bool = False,
        anchor: Anchor = "top-right",
        enable_inhibitor: bool = False,
        keyboard_mode: Keyboard_Mode = "on-demand",
        timeout: int = 1000,
    ):
        self._layer = layer
        self.timeout = timeout
        self.current_timeout = 0
        self.popup_running = False

        self.popup_visible = popup_visible

        self.enable_inhibitor = enable_inhibitor

        self.monitor_number: int | None = None
        self._monitor_toggle_pending = False
        self._monitor_toggle_gen = 0
        self.hyprland_monitor = HyprlandWithMonitors()

        self.reveal_child = PopupRevealer(
            popup_window=self,
            child=child,
            transition_type=transition_type or "slide-down",
            transition_duration=transition_duration,
            decorations=decorations,
            name=name,
        )

        super().__init__(
            name=name,
            title=title,
            layer=self._layer,
            keyboard_mode=keyboard_mode,
            visible=False,
            exclusivity="normal",
            anchor="top bottom right left",
            child=make_layout(
                anchor=anchor,
                name=name,
                popup=self.reveal_child,
                on_button_press_event=self.on_inhibit_click,
            ),
            on_key_release_event=self.on_key_release,
        )
        self.set_property("pass-through", not self.enable_inhibitor)

    def _set_popup_visible(self, visible: bool):
        if not visible:
            self._monitor_toggle_pending = False

        if visible and not self.popup_visible:
            self.reveal_child.revealer.set_visible(True)

        self.popup_visible = visible
        self.reveal_child.revealer.set_reveal_child(visible)

    def on_key_release(self, _, event_key: Gdk.EventKey):
        if event_key.keyval == Gdk.KEY_Escape:
            self._set_popup_visible(False)

    def on_inhibit_click(self, *_):
        self._set_popup_visible(False)

    def toggle_popup(self, monitor: bool = False):
        if monitor:
            self._monitor_toggle_pending = True
            self._monitor_toggle_gen += 1
            gen = self._monitor_toggle_gen
            self.hyprland_monitor.get_current_gdk_monitor_id(
                lambda curr_monitor: self._on_monitor_resolved(curr_monitor, gen)
            )
            return

        self._monitor_toggle_pending = False
        self._set_popup_visible(not self.popup_visible)

    def _on_monitor_resolved(self, curr_monitor, gen):
        # Stale if a dismiss landed mid-flight; it would re-open the popup.
        if not self._monitor_toggle_pending or gen != self._monitor_toggle_gen:
            return
        self._monitor_toggle_pending = False

        if self.monitor_number != curr_monitor and self.popup_visible:
            self.monitor_number = curr_monitor
            return

        self.monitor_number = curr_monitor
        self._set_popup_visible(not self.popup_visible)

    def toggle(self):
        return self.toggle_popup()

    def popup_timeout(self):
        if self.popup_running:
            self.current_timeout = 0
            return

        self.current_timeout = 0
        self._set_popup_visible(True)
        self.popup_running = True

        def popup_func():
            if self.current_timeout >= self.timeout:
                self._set_popup_visible(False)
                self.current_timeout = 0
                self.popup_running = False
                return False
            self.current_timeout += 500
            return True

        self._register_repeater(GLib.timeout_add(500, popup_func))

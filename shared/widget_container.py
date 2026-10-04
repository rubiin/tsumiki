import contextlib
from typing import Callable, Iterable

from fabric.utils import GLib, Gtk, bulk_connect
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.widget import Widget

from utils.functions import safe_disconnect


def _source_is_alive(source_id: int) -> bool:
    """True while *source_id* is still armed on the default main context.

    ``GLib.source_remove`` on a spent id is a GLib-CRITICAL on stderr, so
    callers use this to avoid removing a source that ended by itself.
    """
    return GLib.MainContext.default().find_source_by_id(source_id) is not None


def format_panel_label(template: str, glyph: str = "", **fields: str) -> str:
    """Render a ``label_format`` template into one panel label's markup.

    ``{icon}`` expands to *glyph*, so a widget's icon and text share a single
    label the way ``battery`` and ``window_count`` do. Whitespace left behind
    by a field that rendered empty does not become a gap.
    """
    try:
        markup = template.format(icon=glyph, **fields)
    except (IndexError, KeyError):
        # An unknown field must not take the bar down with it.
        markup = template
    return " ".join(markup.split())


class TeardownMixin:
    """Track GLib timers and signal handlers so ``destroy`` can remove them.

    Cleanup hangs off the ``destroy`` *signal*, not a ``destroy()`` override:
    GTK destroys children from C, which never dispatches to a Python override.
    """

    def _ensure_teardown_hooked(self) -> None:
        """Connect ``_teardown`` to ``destroy`` once, on first tracked resource."""
        if hasattr(self, "_repeaters"):
            return
        self._repeaters = []
        self._handlers = []
        self.connect("destroy", self._teardown)

    def _register_repeater(self, repeater_id: int) -> int:
        """Track *repeater_id* until it is removed or ends on its own.

        Sources that already fired are pruned here: a widget that re-arms on
        every keystroke would otherwise accumulate a dead id per keystroke.
        """
        self._ensure_teardown_hooked()
        self._repeaters = [r for r in self._repeaters if _source_is_alive(r)]
        self._repeaters.append(repeater_id)
        return repeater_id

    def _add_repeater(self, interval_ms: int, callback: Callable[..., bool], *args):
        """Arm a tracked repeater that untracks itself when it returns ``False``.

        Only a source this mixin created can be dropped on its own, which is why
        one-shot timers should be armed here rather than by handing in an id.
        """

        def fire() -> bool:
            if callback(*args):
                return True
            self._unregister_repeater(repeater_id)
            return False

        repeater_id = GLib.timeout_add(interval_ms, fire)
        return self._register_repeater(repeater_id)

    def _unregister_repeater(self, repeater_id: int) -> None:
        """Remove a repeater id from the tracked list after manual removal."""
        with contextlib.suppress(ValueError):
            getattr(self, "_repeaters", []).remove(repeater_id)

    def _register_handler(self, source, handler_id) -> int:
        self._ensure_teardown_hooked()
        self._handlers.append((source, handler_id))
        return handler_id

    def _unregister_handler(self, source, handler_id) -> None:
        """Forget a tracked handler after it has been disconnected by hand."""
        with contextlib.suppress(ValueError):
            getattr(self, "_handlers", []).remove((source, handler_id))

    def _register_handlers(self, source, signal_map: dict[str, Callable]) -> list[int]:
        """Tracked counterpart of ``bulk_connect``, so ids reach ``_teardown``."""
        return [
            self._register_handler(source, source.connect(signal, callback))
            for signal, callback in signal_map.items()
        ]

    def _timeout_store(self) -> dict[str, int]:
        self._ensure_teardown_hooked()
        if not hasattr(self, "_timeouts"):
            self._timeouts = {}
        return self._timeouts

    def _tick_store(self) -> dict[str, tuple[object, int]]:
        self._ensure_teardown_hooked()
        if not hasattr(self, "_ticks"):
            self._ticks = {}
        return self._ticks

    def _has_timeout(self, key: str) -> bool:
        """True while a timer armed under *key* has not fired yet."""
        return key in self._timeout_store()

    def _has_tick(self, key: str) -> bool:
        """True while a frame-clock tick armed under *key* is still pending."""
        return key in self._tick_store()

    def _schedule_repeater(
        self,
        key: str,
        interval_ms: int,
        callback: Callable[[], bool],
    ) -> bool:
        """Arm a repeating timer under *key*; return whether it was armed.

        Keyed like :meth:`_schedule_timeout` but keeps firing until *callback*
        returns ``False``, at which point the key is freed.
        """
        if self._has_timeout(key):
            return False
        store = self._timeout_store()

        def fire() -> bool:
            if callback():
                return True
            # Free the key before returning so a re-arm is not clobbered.
            store.pop(key, None)
            return False

        store[key] = GLib.timeout_add(interval_ms, fire)
        return True

    def _schedule_tick(self, widget, key: str, callback: Callable[..., bool]) -> bool:
        """Arm a frame-clock tick on *widget* under *key*.

        A tick self-throttles to the display's refresh rate and is only serviced
        while the widget is actually being drawn, unlike a fixed ``timeout_add``.
        """
        if self._has_tick(key):
            return False
        self._tick_store()[key] = (widget, widget.add_tick_callback(callback))
        return True

    def _cancel_tick(self, key: str) -> None:
        """Cancel a tick armed by :meth:`_schedule_tick`, if one is pending."""
        entry = getattr(self, "_ticks", {}).pop(key, None)
        if entry is not None:
            widget, tick_id = entry
            widget.remove_tick_callback(tick_id)

    def _schedule_timeout(
        self,
        key: str,
        delay_ms: int,
        callback: Callable[[], bool],
        *,
        replace: bool = False,
    ) -> bool:
        """Arm a one-shot timer under *key*; return whether it was armed.

        A pending timer for the same key survives unless ``replace=True``.
        """
        if self._has_timeout(key) and not replace:
            return False
        self._cancel_timeout(key)
        self._timeout_store()[key] = GLib.timeout_add(
            delay_ms, self._fire_timeout(key, callback)
        )
        return True

    def _fire_timeout(self, key: str, callback: Callable[[], bool]):
        def fire() -> bool:
            # Drop the key before running so a re-arming callback is not clobbered.
            self._timeout_store().pop(key, None)
            return callback()

        return fire

    def _cancel_timeout(self, key: str) -> None:
        """Cancel a timer armed by :meth:`_schedule_timeout`, if one is pending."""
        store = getattr(self, "_timeouts", None) or {}
        if key in store:
            GLib.source_remove(store.pop(key))

    def _teardown(self, *_):
        for repeater_id in list(getattr(self, "_repeaters", [])):
            if repeater_id and _source_is_alive(repeater_id):
                GLib.source_remove(repeater_id)
        for timeout_id in getattr(self, "_timeouts", {}).values():
            if timeout_id:
                GLib.source_remove(timeout_id)
        for widget, tick_id in getattr(self, "_ticks", {}).values():
            widget.remove_tick_callback(tick_id)
        for source, handler_id in getattr(self, "_handlers", []):
            safe_disconnect(source, handler_id)
        self._repeaters = []
        self._handlers = []
        self._timeouts = {}
        self._ticks = {}

    def toggle(self):
        """Toggle the visibility of this widget/window."""
        if self.is_visible():
            self.hide()
        else:
            self.show()


def tooltips_enabled() -> bool:
    """Read ``general.tooltips`` — the global kill switch for every tooltip.

    For hosts that are not a :class:`BaseWidget` and cache no copy of the flag.
    """
    # Deferred: importing utils.config parses config.toml and validates it.
    from utils.config import tsumiki_config

    return tsumiki_config.get("general", {}).get("tooltips", True)


class BaseWidget(Widget, TeardownMixin):
    """A base widget class that can be extended for custom widgets."""

    @staticmethod
    def _merge_style_classes(
        defaults: list[str],
        style_classes: str | Iterable[str] | None,
    ) -> list[str]:
        merged = list(defaults)
        if style_classes is None:
            return merged

        if isinstance(style_classes, str):
            merged.append(style_classes)
        else:
            merged.extend(style_classes)
        return merged

    def _init_widget_settings(self, widget_name: str) -> None:
        # Deferred: importing utils.config parses config.toml and validates it.
        from utils.config import tsumiki_config

        self.config: dict = tsumiki_config.get("widgets", {}).get(widget_name, {})
        self.general_config: dict = tsumiki_config.get("general", {})
        self.tooltips_enabled = self.general_config.get("tooltips", True)

    def format_shows_icon(
        self, key: str = "label_format", default: str = "{icon}"
    ) -> bool:
        """True when the widget's format string asks for the ``{icon}`` field.

        Replaces the old ``show_icon`` toggle: an icon is rendered when the
        format string mentions ``{icon}``, and dropped when it does not.
        """
        label_format = self.config.get(key, default)
        return isinstance(label_format, str) and "{icon}" in label_format

    def _connect_hover_reveal(self) -> None:
        if not self.config.get("hover_reveal", True):
            return

        bulk_connect(
            self,
            {
                "enter-notify-event": self._toggle_revealer,
                "leave-notify-event": self._toggle_revealer,
            },
        )

    def toggle_css_class(self, class_name: str | Iterable[str], condition: bool):
        if condition:
            self.add_style_class(class_name)
        else:
            self.remove_style_class(class_name)

    def _toggle_revealer(self, *_):
        if hasattr(self, "revealer"):
            self.revealer.set_reveal_child(not self.revealer.get_reveal_child())

    def set_active_style(self, action: bool, *_) -> None:
        self.set_style_classes("") if not action else self.set_style_classes("active")

    def _sync_hover_cursor(self, *_):
        """Point at a hand while prelit, and back to the default after.

        Goes through the guarded helper: the bare widget setter rebuilds a
        Gdk.Cursor per call and raises before the widget has a window.
        """
        from utils.widget_utils import set_cursor

        hovered = bool(self.get_state_flags() & Gtk.StateFlags.PRELIGHT)
        set_cursor(self, "pointer" if hovered else "default")

    def set_tooltip_if_enabled(self, text: str, default: bool = False) -> None:
        """Set tooltip text only when tooltips are enabled.

        *default* is the fallback when ``widgets.<name>.tooltip`` is absent.
        """
        if self.config.get("tooltip", default) and self.tooltips_enabled:
            self.set_tooltip_text(text)


class BaseWindow(Window, TeardownMixin):
    """A base window class that can be extended for custom windows."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class BoxWidget(Box, BaseWidget):
    """A container for box widgets."""

    def __init__(self, spacing=None, style_classes=None, **kwargs):
        all_styles = self._merge_style_classes(["panel-box"], style_classes)

        super().__init__(
            spacing=4 if spacing is None else spacing,
            style_classes=all_styles,
            **kwargs,
        )

        widget_name = kwargs.get("name", "box")
        self._init_widget_settings(widget_name)


class EventBoxWidget(EventBox, BaseWidget):
    """A container for box widgets."""

    def __init__(self, **kwargs):
        super().__init__(
            style_classes="panel-eventbox",
            **kwargs,
        )

        widget_name = kwargs.get("name", "eventbox")
        self._init_widget_settings(widget_name)
        self.container_box = Box(name="widget-container", style_classes="panel-box")
        self.add(
            self.container_box,
        )
        self._connect_hover_reveal()
        from utils.widget_utils import setup_cursor_hover

        setup_cursor_hover(self)


class ButtonWidget(Button, BaseWidget):
    """A container for button widgets. Only used for new widgets that are used on bar"""

    def __init__(self, **kwargs):
        super().__init__(
            style_classes="panel-button",
            **kwargs,
        )

        widget_name = kwargs.get("name", "button")
        self._init_widget_settings(widget_name)

        self.container_box = Box(style_classes="widget-container")
        self.add(self.container_box)
        self._connect_hover_reveal()

        self.connect("state-flags-changed", self._sync_hover_cursor)

    def add_panel_content(
        self,
        icon: str | Widget | None,
        label: str | Widget | None = None,
        *,
        show_label: bool = True,
    ) -> None:
        """Fill the container box with the panel icon and an optional label.

        Either argument may be an already-built widget that updates its own text.
        A *None* icon leaves the label as the only panel content.
        """
        # Deferred: this module must import without the user's config.
        from utils.widget_utils import nerd_font_icon

        if icon is None:
            self.container_box.children = ()
        elif isinstance(icon, Widget):
            self.container_box.children = (icon,)
        else:
            self.container_box.children = (
                nerd_font_icon(icon=icon, props={"style_classes": ["panel-font-icon"]}),
            )

        if show_label and label is not None:
            self.container_box.add(
                label
                if isinstance(label, Widget)
                else Label(label=label, style_classes="panel-text")
            )

    def add_formatted_label(
        self, template: str, glyph: str = "", **fields: str
    ) -> Label:
        """Add the single panel label that ``label_format`` drives.

        *glyph* fills ``{icon}`` and *fields* the widget's own placeholders, so
        icon and text share one label instead of two sibling widgets. The
        ``panel-format`` class is what per-widget icon sizing keys off now.
        """
        self.panel_label = Label(style_classes=["panel-text", "panel-format"])
        self.container_box.add(self.panel_label)
        self.refresh_formatted_label(glyph, **fields)
        return self.panel_label

    def refresh_formatted_label(self, glyph: str = "", **fields: str) -> None:
        """Re-render the panel label after the widget's state changed."""
        template = getattr(self, "label_format", "{icon}")
        self.panel_label.set_markup(format_panel_label(template, glyph, **fields))


class WidgetGroup(BoxWidget):
    """A group of widgets that can be managed and styled together."""

    def __init__(
        self,
        children=None,
        spacing=4,
        style_classes=None,
        hover_reveal=False,
        reveal_duration=500,
        revealer_icon=None,
        **kwargs,
    ):
        css_classes = self._merge_style_classes(["panel-module-group"], style_classes)

        self._hover_reveal = hover_reveal

        super().__init__(
            name="widget-group",
            spacing=spacing,
            style_classes=css_classes,
            orientation="h",
            **kwargs,
        )

        if hover_reveal:
            self._setup_hover_reveal(children, reveal_duration, revealer_icon or "󰍽")
        elif children:
            for child in children:
                self.add(child)

    def _setup_hover_reveal(self, children, reveal_duration, icon_char):
        """Wrap children in a revealer and add a reveal icon."""
        self.revealer_icon = Label(
            name="widget-group-revealer-icon",
            label=icon_char,
            style_classes="panel-font-icon",
        )
        self.add(self.revealer_icon)

        children_box = Box(
            orientation="h",
            spacing=self._spacing,
            style_classes="panel-module-group-inner",
        )
        if children:
            for child in children:
                children_box.add(child)

        self.revealer = Revealer(
            child=children_box,
            transition_duration=reveal_duration,
            transition_type="slide_right",
            reveal_child=False,
        )
        self.add(self.revealer)

        bulk_connect(
            self,
            {
                "enter-notify-event": self._on_hover_enter_reveal,
                "leave-notify-event": self._on_hover_leave_reveal,
            },
        )

    def _on_hover_enter_reveal(self, *_):
        if not self._hover_reveal:
            return
        self.revealer.set_reveal_child(True)

    def _on_hover_leave_reveal(self, *_):
        if not self._hover_reveal:
            return
        self.revealer.set_reveal_child(False)

    @classmethod
    def from_config(cls, config, widgets_list, main_config=None):
        from utils.widget_factory import WidgetResolver

        resolver = WidgetResolver(widgets_list)
        context = {"config": main_config} if main_config else {}

        widgets = resolver.batch_resolve(config.get("widgets", []), context)

        return cls(
            children=widgets,
            spacing=config.get("spacing", 4),
            style_classes=config.get("style_classes", []),
            hover_reveal=config.get("hover_reveal", False),
            reveal_duration=config.get("reveal_duration", 500),
            revealer_icon=config.get("revealer_icon", None),
        )

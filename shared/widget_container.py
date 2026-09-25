from typing import Callable, Iterable

from fabric.utils import GLib, bulk_connect
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.widget import Widget

from utils.functions import safe_disconnect


class TeardownMixin:
    """Track GLib repeaters and signal handlers for teardown on destroy.

    Widgets call ``_register_repeater`` / ``_register_handler``; the first call
    wires a ``destroy`` handler that removes every tracked source. This stops
    the leaks that stack when bars are recreated on config edit / hotplug.
    """

    def _register_repeater(self, repeater_id: int) -> int:
        if not hasattr(self, "_repeaters"):
            self._repeaters = []
            self._handlers = []
            self.connect("destroy", self._teardown)
        self._repeaters.append(repeater_id)
        return repeater_id

    def _unregister_repeater(self, repeater_id: int) -> None:
        """Remove a repeater id from the tracked list after manual removal."""
        import contextlib

        with contextlib.suppress(ValueError):
            getattr(self, "_repeaters", []).remove(repeater_id)

    def _register_handler(self, source, handler_id) -> int:
        if not hasattr(self, "_repeaters"):
            self._repeaters = []
            self._handlers = []
            self.connect("destroy", self._teardown)
        self._handlers.append((source, handler_id))
        return handler_id

    def _register_handlers(self, source, signal_map: dict[str, Callable]) -> list[int]:
        """Connect every signal in *signal_map* on *source*, tracked for teardown.

        This is the tracked counterpart of fabric's ``bulk_connect``. The plain
        call returns the handler ids and throws them away, which is what lets
        those connections outlive the widget; here they all go to ``_teardown``.
        """
        return [
            self._register_handler(source, source.connect(signal, callback))
            for signal, callback in signal_map.items()
        ]

    def _timeout_store(self) -> dict[str, int]:
        if not hasattr(self, "_timeouts"):
            self._timeouts = {}
        return self._timeouts

    def _has_timeout(self, key: str) -> bool:
        """True while a timer armed under *key* has not fired yet."""
        return key in self._timeout_store()

    def _schedule_timeout(
        self,
        key: str,
        delay_ms: int,
        callback: Callable[[], bool],
        *,
        replace: bool = False,
    ) -> bool:
        """Arm a one-shot timer under *key*; return whether it was armed.

        A pending timer for the same key is left alone by default, which is
        what a debounce wants: repeated events collapse into the one already
        armed. Pass ``replace=True`` for a timer that must count from the
        latest call.

        The timer is tracked for teardown, so a widget cannot leak one by
        forgetting to cancel it. A repeating poll re-arms itself from inside the
        callback; *key* is free by then.
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
            # The source is spent once it fires: drop the key before running so
            # a callback that re-arms the same key is not clobbered.
            self._timeout_store().pop(key, None)
            return callback()

        return fire

    def _cancel_timeout(self, key: str) -> None:
        """Cancel a timer armed by :meth:`_schedule_timeout`, if one is pending."""
        store = getattr(self, "_timeouts", None) or {}
        if key in store:
            GLib.source_remove(store.pop(key))

    def _teardown(self, *_):
        for repeater_id in getattr(self, "_repeaters", []):
            if repeater_id:
                GLib.source_remove(repeater_id)
        for timeout_id in getattr(self, "_timeouts", {}).values():
            if timeout_id:
                GLib.source_remove(timeout_id)
        for source, handler_id in getattr(self, "_handlers", []):
            safe_disconnect(source, handler_id)
        self._repeaters = []
        self._handlers = []
        self._timeouts = {}

    def toggle(self):
        """Toggle the visibility of this widget/window."""
        if self.is_visible():
            self.hide()
        else:
            self.show()


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
        # Imported here rather than at module scope: importing utils.config
        # parses config.toml and validates it against the ~122 KB schema, a cost
        # anything that merely imports this shared widget layer should not pay.
        from utils.config import tsumiki_config

        self.config: dict = tsumiki_config.get("widgets", {}).get(widget_name, {})
        self.general_config: dict = tsumiki_config.get("general", {})
        self.tooltips_enabled = self.general_config.get("tooltips", True)

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

    def set_tooltip_if_enabled(self, text: str, default: bool = False) -> None:
        """Set tooltip text only when tooltips are enabled.

        Replaces the two-line guard in almost every widget:
            ``if self.config.get("tooltip", ...) and self.tooltips_enabled:``

        Args:
            text: The tooltip string to display.
            default: Fallback when ``widgets.<name>.tooltip`` is absent.
                Use ``True`` for widgets whose tooltip is on by convention.
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

        self.connect(
            "state-flags-changed",
            lambda btn, *_: (
                btn.set_cursor("pointer")
                if btn.get_state_flags() & 2  # type: ignore
                else btn.set_cursor("default"),
            ),
        )

    def add_panel_content(
        self,
        icon: str | Widget,
        label: str | Widget | None = None,
        *,
        show_label: bool = True,
    ) -> None:
        """Fill the container box with the panel icon and an optional label.

        Every panel widget is an icon plus, optionally, a text label; the only
        per-widget differences are whether the label is enabled and what it
        says. Either argument may be an already-built widget, for the widgets
        that need a revealer or update their text later.
        """
        # Imported here, not at module scope: utils.widget_utils reaches
        # utils.config, and this module must stay importable without loading
        # the user's configuration (see test_config.ConfigImportIsolationTest).
        from utils.widget_utils import nerd_font_icon

        self.container_box.children = (
            icon
            if isinstance(icon, Widget)
            else nerd_font_icon(icon=icon, props={"style_classes": ["panel-font-icon"]})
        )

        if show_label and label is not None:
            self.container_box.add(
                label
                if isinstance(label, Widget)
                else Label(label=label, style_classes="panel-text")
            )


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

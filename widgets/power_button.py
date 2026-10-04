from fabric.utils import Gdk, GLib, Gtk, exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.grid import Grid
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.svg import Svg
from fabric.widgets.widget import Widget

from shared.buttons import HoverButton
from shared.dialog import Dialog
from shared.popup import PopupWindow
from shared.widget_container import ButtonWidget
from utils.constants import ASSETS_DIR
from utils.i18n import _


class PowerMenuPopup(PopupWindow):
    """A popup window to show power options."""

    def __init__(
        self,
        config: dict,
        **kwargs,
    ):
        self._bar_visibility: list[tuple[Widget, bool]] = []
        self._power_buttons: list[PowerControlButtons] = []
        self._digit_shortcuts: dict[str, PowerControlButtons] = {}
        self._letter_shortcuts: dict[str, PowerControlButtons] = {}
        self.icon_size = config.get("icon_size", 16)

        self.icon_dir = f"{ASSETS_DIR}/icons/svg/"
        power_buttons_list = config.get("buttons", [])
        self._configured_shortcuts: dict[str, str] = config.get("item_shortcuts", {})
        power_button_names = list(power_buttons_list)

        self.grid = Grid(
            name="power-button-menu",
            column_homogeneous=True,
            row_homogeneous=True,
        )

        self._power_buttons = [
            PowerControlButtons(
                config=config,
                name=value,
                command=power_buttons_list[value],
                size=self.icon_size,
                parent=self,
                icon_path=self.icon_dir,
            )
            for value in power_button_names
        ]

        self.grid.attach_flow(
            children=self._power_buttons,
            columns=config.get("items_per_row", 3),
        )

        self._setup_item_shortcuts()

        super().__init__(
            child=self.grid,
            transition_duration=400,
            transition_type="slide-down",
            anchor="center",
            enable_inhibitor=True,
            keyboard_mode="exclusive",
            name="power-menu-overlay",
            layer="top",
            **kwargs,
        )

    def _setup_item_shortcuts(self):
        self._digit_shortcuts.clear()
        self._letter_shortcuts.clear()
        buttons_by_name = {button.name: button for button in self._power_buttons}

        for button in self._power_buttons:
            button.set_shortcut(None)

        for item_name, shortcut in self._configured_shortcuts.items():
            button = buttons_by_name.get(item_name)
            if button is None or not isinstance(shortcut, str) or not shortcut:
                continue
            self._letter_shortcuts[shortcut[0].lower()] = button

        for index, button in enumerate(self._power_buttons, start=1):
            if index <= 9:
                self._digit_shortcuts[str(index)] = button

            first_letter = button.name[:1].lower()
            if first_letter and first_letter not in self._letter_shortcuts:
                self._letter_shortcuts[first_letter] = button

        for shortcut, button in self._letter_shortcuts.items():
            button.set_shortcut(shortcut.upper())

    @staticmethod
    def _keyval_to_char(keyval: int) -> str:
        value = Gdk.keyval_to_unicode(keyval)
        if value <= 0:
            return ""
        return chr(value).lower()

    def _activate_button(self, button: "PowerControlButtons") -> bool:
        if button is None:
            return False
        return bool(button.on_button_press())

    def _activate_focused_button(self) -> bool:
        for button in self._power_buttons:
            if button.has_focus():
                return self._activate_button(button)
        return False

    def _set_popup_visible(self, visible: bool):
        super()._set_popup_visible(visible)
        self.set_panel_visibility(visible)

    def set_panel_visibility(self, popup_visible: bool):
        from fabric import Application

        app = Application.get_default()
        if app is None:
            return

        if popup_visible:
            cached_visibility: list[tuple[Gtk.Widget, bool]] = []
            for window in app.get_windows():
                if window is self or window.get_name() != "panel":
                    continue
                visible = window.get_visible()
                cached_visibility.append((window, visible))

            self._bar_visibility = cached_visibility

            def hide_bars():
                for window, was_visible in self._bar_visibility:
                    if was_visible:
                        window.set_visible(False)
                return False

            GLib.idle_add(hide_bars)
            return

        cached_visibility = list(self._bar_visibility)
        self._bar_visibility = []

        def restore_bars():
            for window, was_visible in cached_visibility:
                window.set_visible(was_visible)
            return False

        GLib.idle_add(restore_bars)

    def on_key_release(self, _, event_key: Gdk.EventKey):
        if event_key.keyval == Gdk.KEY_Escape:
            return super().on_key_release(_, event_key)

        if not self.popup_visible:
            return False

        if event_key.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            return self._activate_focused_button()

        pressed = self._keyval_to_char(event_key.keyval)
        if not pressed:
            return False

        button = self._digit_shortcuts.get(pressed) or self._letter_shortcuts.get(
            pressed
        )
        if button is None:
            return False

        return self._activate_button(button)

    def set_action_buttons_focus(self, can_focus: bool):
        for child in self.grid.get_children():
            child: Widget = child
            child.set_can_focus(can_focus)

    def toggle(self):
        self.set_action_buttons_focus(True)
        result = super().toggle_popup()
        if self.popup_visible and self._power_buttons:
            self._power_buttons[0].grab_focus()
        return result


class PowerControlButtons(HoverButton):
    """A widget to show power options."""

    def __init__(
        self,
        config: dict,
        parent: PopupWindow,
        name: str,
        command: str,
        icon_path: str,
        size: int,
        show_label=True,
        **kwargs,
    ):
        self.config = config
        self.name = name
        self.command = command
        self.size = size
        self.parent = parent

        self.container_box = Box(
            style_classes="power-button-container",
            orientation="v",
            children=[
                Svg(
                    svg_file=f"{icon_path}/{name}.svg",
                    size=size,
                    name="svg-icon",
                ),
            ],
        )

        self.shortcut_label = Label(
            label="",
            style_classes="power-shortcut-label",
            h_align="start",
            v_align="start",
            visible=False,
        )

        self.overlay_box = Overlay(
            child=self.container_box,
            overlays=[self.shortcut_label],
        )

        super().__init__(
            config=config,
            orientation="v",
            name="power-control-button",
            on_clicked=self.on_button_press,
            child=self.overlay_box,
            **kwargs,
        )

        if show_label:
            self.container_box.add(
                Label(
                    label=name.capitalize(),
                    style_classes="panel-text",
                )
            )

    def set_shortcut(self, shortcut: str | None):
        if not shortcut:
            self.shortcut_label.set_visible(False)
            self.shortcut_label.set_label("")
            return

        self.shortcut_label.set_label(shortcut[:1].upper())
        self.shortcut_label.set_visible(True)

    def on_button_press(self, *_args):
        self.parent.toggle_popup()
        if self.config.get("confirm", True):
            Dialog().add_content(
                title=_("widget.power.confirmation", name=self.name.capitalize()),
                body=_("widget.power.confirm_action", name=self.name),
                command=self.command,
            ).toggle_popup()
        else:
            exec_shell_command_async(self.command, lambda *_: None)

        return True


class PowerWidget(ButtonWidget):
    """A widget to power off the system."""

    def show_popover(self, *_):
        """Show the popover."""
        if self.popup is None:
            self.popup = PowerMenuPopup(self.config)
        self.popup.toggle()

    def __init__(self, **kwargs):
        super().__init__(name="power", **kwargs)

        self.popup = None

        self.label_format = self.config.get("label_format", "{icon} power")
        self.add_formatted_label(self.label_format, self.config.get("icon", ""))

        self.set_tooltip_if_enabled(_("widget.power.tooltip"))

        self.connect(
            "clicked",
            self.show_popover,
        )

from collections.abc import Callable
from functools import partial

from fabric.core.service import Signal
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from utils.constants import ASSETS_DIR
from utils.icons import get_symbolic_icon, get_text_icon
from utils.widget_utils import nerd_font_icon, setup_cursor_hover

from .animator import cubic_bezier
from .circle_image import CircularImage
from .submenu import QuickSubMenu
from .widget_container import BaseWidget


class HoverButton(Button, BaseWidget):
    """A container for button with hover effects."""

    def __init__(self, **kwargs):
        super().__init__(
            **kwargs,
        )

        setup_cursor_hover(self)
        # Panel buttons must stay keyboard-focusable (GNOME HIG / GTK a11y).
        self.set_can_focus(True)


class ScanButton(HoverButton):
    """A button to start a scan action."""

    def __init__(self, **kwargs):
        super().__init__(name="scan-button", style_classes="submenu-button", **kwargs)

        self.scan_image = CircularImage(
            image_file=f"{ASSETS_DIR}icons/svg/refresh.svg",
            size=kwargs.get("size", 20),
        )
        self.scan_animator = None

        self.set_image(self.scan_image)

    def set_notify_value(self, p, *_):
        self.scan_image.set_angle(p.value)

    def play_animation(self):
        from .animator import Animator

        if self.scan_animator is None:
            self.scan_animator = Animator(
                timing_function=partial(cubic_bezier, 0, 0, 1, 1),
                duration=4,
                min_value=0,
                max_value=360,
                tick_widget=self,
                notify_value=self.set_notify_value,
            )
        self.scan_animator.play()

    def stop_animation(self):
        self.scan_animator.stop()


class QSToggleButton(Box, BaseWidget):
    """A widget to display a toggle button for quick settings."""

    @Signal
    def action_clicked(self) -> None: ...

    def __init__(
        self,
        action_label: str = "My Label",
        action_icon: str = get_text_icon("ui.package", ""),
        action_title: str | None = None,
        pixel_size: int = 20,
        **kwargs,
    ):
        self.pixel_size = pixel_size

        # The default size lives in SCSS (.quicksettings-toggle-icon); a
        # non-default size falls back to an inline override only when needed.
        icon_props: dict = {
            "style_classes": ["panel-font-icon", "quicksettings-toggle-icon"],
        }
        if self.pixel_size != 20:
            icon_props["style"] = f"font-size: {self.pixel_size}px;padding-left: 6px;"

        # Action button can hold an icon and a label NOTHING MORE
        self.action_icon = nerd_font_icon(
            icon=action_icon,
            props=icon_props,
        )

        # With a title the action label becomes the status line beneath it.
        self.action_title = Label(
            style_classes=["panel-text", "quicksettings-tile-title"],
            label=action_title if action_title is not None else action_label,
            ellipsization="end",
            h_align="start",
            h_expand=True,
        )

        self.action_label = Label(
            style_classes=["panel-text", "quicksettings-tile-status"],
            label=action_label if action_title is not None else "",
            ellipsization="end",
            h_align="start",
            h_expand=True,
        )

        self._action_content = Box(
            h_align="start",
            v_align="center",
            spacing=10,
            style_classes="quicksettings-toggle-action-box",
            children=[
                self.action_icon,
                Box(
                    orientation="v",
                    v_align="center",
                    h_expand=True,
                    children=[self.action_title, self.action_label],
                ),
            ],
        )

        self.action_button = HoverButton(
            style_classes="quicksettings-toggle-action",
            on_clicked=self._action,
            child=self._action_content,
            h_expand=True,
        )

        self.action_button.set_size_request(170, 20)
        if self.action_title:
            self.action_button.set_tooltip_text(self.action_title.get_label())

        # h_expand fills the cell; the button absorbs it so the chevron pins right.
        self.box = Box(children=[self.action_button], h_expand=True)

        super().__init__(
            name="quicksettings-togglebutton",
            v_align="start",
            children=[self.box],
            **kwargs,
        )

    def _action(self, *_):
        self.emit("action-clicked")

    def set_action_label(self, label: str):
        self.action_label.set_label(label.strip())

    def set_action_title(self, title: str):
        self.action_title.set_label(title.strip())

    def set_action_icon(self, icon: str):
        self.action_icon.set_label(icon)


class QSChevronButton(QSToggleButton):
    """A widget to display a toggle button for quick settings."""

    @Signal
    def reveal_clicked(self) -> None: ...

    def __init__(
        self,
        action_label: str = "My Label",
        action_icon: str = get_symbolic_icon("fallback.package"),
        action_title: str | None = None,
        pixel_size: int = 20,
        submenu: QuickSubMenu | None = None,
        submenu_factory: Callable[[], QuickSubMenu] | None = None,
        **kwargs,
    ):
        self.submenu = submenu
        self._submenu_factory = submenu_factory

        self.button_image = Image(
            icon_name=get_symbolic_icon("ui.arrow.right"), icon_size=20
        )

        self.reveal_button = HoverButton(
            style_classes="toggle-revealer",
            image=self.button_image,
            on_clicked=self._reveal_toggle,
        )

        super().__init__(
            action_label,
            action_icon,
            action_title,
            pixel_size,
            **kwargs,
        )
        # Fixed width packed right; the button's h_expand absorbs the rest.
        self.box.pack_end(self.reveal_button, False, False, 0)

        if self.submenu is not None:
            self.submenu.revealer.connect(
                "notify::reveal-child",
                self.set_chevron_icon,
            )

    def ensure_submenu(self) -> QuickSubMenu | None:
        """Build the submenu lazily on first use, then return it."""
        if self.submenu is None and self._submenu_factory is not None:
            self.submenu = self._submenu_factory()
            if self.submenu is not None:
                self.submenu.revealer.connect(
                    "notify::reveal-child",
                    self.set_chevron_icon,
                )
        return self.submenu

    def set_chevron_icon(self, *_):
        if self.submenu is None:
            return
        icon_name = (
            get_symbolic_icon("ui.arrow.down")
            if self.submenu.revealer.get_reveal_child()
            else get_symbolic_icon("ui.arrow.right")
        )
        self.button_image.set_from_icon_name(icon_name, 20)

    def _reveal_toggle(self, *_):
        if self.ensure_submenu() is None:
            return
        self.emit("reveal-clicked")

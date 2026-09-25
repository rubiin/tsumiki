from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.widget import Widget

from utils.widget_utils import nerd_font_icon


def scrolled_list_content(
    child: Widget,
    *,
    min_height: int = -1,
    max_height: int = 260,
    v_expand: bool = False,
) -> ScrolledWindow:
    """Wrap a submenu's list content in the shared scroll configuration.

    ``propagate_width=False`` plus an automatic horizontal policy is what keeps
    long labels from widening the popup - GTK3 ignores the policy entirely when
    it is set to "never", so it has to stay "automatic".
    """
    return ScrolledWindow(
        min_content_size=(-1, min_height),
        max_content_size=(-1, max_height),
        propagate_width=False,
        propagate_height=True,
        v_expand=v_expand,
        h_scrollbar_policy="automatic",
        v_scrollbar_policy="automatic",
        child=child,
    )


class QuickSubMenu(Box):
    """A widget to display a submenu for quick settings."""

    def __init__(
        self,
        scan_button: Button | None,
        child: Widget | None,
        title: str | None = None,
        title_icon: str | None = None,
        **kwargs,
    ):
        super().__init__(visible=False, **kwargs)
        self.title = title
        self.title_icon = title_icon
        self.child = child
        self.scan_button = scan_button

        self.revealer_child = Box(orientation="v", name="submenu")

        self.submenu_title_box = self.make_submenu_title_box()

        self.revealer_child.add(
            self.submenu_title_box
        ) if self.submenu_title_box else None

        self.revealer_child.add(self.child) if child else None

        self.revealer = Revealer(
            child=self.revealer_child,
            transition_type="slide-down",
            transition_duration=250,
            h_expand=True,
        )
        self.revealer.connect(
            "notify::child-revealed",
            self.on_child_revealed,
        )

        self.add(self.revealer)

    def on_child_revealed(self, revealer: Revealer, *_):
        self.set_visible(revealer.get_reveal_child())

    def make_submenu_title_box(self) -> Box | None:
        submenu_box = Box(spacing=4, style_classes="submenu-title-box")

        if not self.title_icon and not self.title:
            return None

        if self.title_icon:
            submenu_box.add(
                nerd_font_icon(
                    icon=self.title_icon,
                    props={
                        "style_classes": ["panel-font-icon"],
                    },
                )
            )
        if self.title:
            submenu_box.add(
                Label(
                    style_classes="submenu-title-label",
                    label=self.title,
                    h_expand=True,
                    h_align="start",
                    ellipsization="end",
                )
            )

        if self.scan_button is not None:
            submenu_box.pack_end(
                self.scan_button,
                False,
                False,
                0,
            )

        return submenu_box

    def _reveal(self, visible: bool):
        self.set_visible(True)
        self.revealer.set_reveal_child(visible)

    def toggle_reveal(self) -> bool:
        self.set_visible(True)
        self.revealer.set_reveal_child(not self.revealer.get_reveal_child())
        return self.revealer.get_reveal_child()

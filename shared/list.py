from collections.abc import Iterable
from typing import Literal

from fabric.utils import Gtk
from fabric.widgets.widget import Widget

from utils.widget_utils import setup_cursor_hover


def next_batch_size(loaded: int, total: int, batch_size: int) -> int:
    """How many more items a batched list can take this pass."""
    return max(0, min(batch_size, total - loaded))


def add_list_row(
    listbox: Gtk.ListBox,
    row: Gtk.Widget,
    spacing: int = 4,
) -> None:
    """Append *row* with a consistent gap between list items."""
    if listbox.get_children():
        row.set_margin_top(spacing)
    listbox.add(row)


def near_list_end(adjustment: Gtk.Adjustment, threshold: int = 50) -> bool:
    """Whether a vertical adjustment is within *threshold* px of its end.

    *threshold* must stay positive: GTK3 ignores a "never" scrollbar policy.
    """
    return (
        adjustment.get_value() + adjustment.get_page_size()
        >= adjustment.get_upper() - threshold
    )


class SubmenuRowMixin:
    """Shared styling for quick-settings submenu list rows.

    ``Gtk.ListBoxRow`` has no ``style_classes`` kwarg, so the classes go
    straight onto its style context.
    """

    def setup_submenu_row(
        self,
        content: Gtk.Widget,
        style_class: str | None = None,
    ) -> None:
        """Apply the shared row style, add *content* and make it focusable."""
        style_context = self.get_style_context()
        style_context.add_class("submenu-button")
        if style_class:
            style_context.add_class(style_class)
        self.add(content)
        self.set_can_focus(True)
        setup_cursor_hover(self)
        self._submenu_row_content = content

    def set_row_active(self, active: bool) -> None:
        """Toggle the ``active`` class on the row content."""
        if active:
            self._submenu_row_content.add_style_class("active")
        else:
            self._submenu_row_content.remove_style_class("active")


class ListBox(Gtk.ListBox, Widget):
    """A simple widget to create a list box with various properties."""

    def __init__(
        self,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes: Iterable[str] | str | None = None,
        tooltip_text: str | None = None,
        tooltip_markup: str | None = None,
        h_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        v_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        h_expand: bool = False,
        v_expand: bool = False,
        size: Iterable[int] | int | None = None,
        **kwargs,
    ):
        Gtk.ListBox.__init__(self)
        Widget.__init__(
            self,
            name,
            visible,
            all_visible,
            style,
            style_classes,
            tooltip_text,
            tooltip_markup,
            h_align,
            v_align,
            h_expand,
            v_expand,
            size,
            **kwargs,
        )

    def remove_all(self) -> None:
        """Remove all children from the list box."""
        for child in self.get_children():
            self.remove(child)
            child.destroy()

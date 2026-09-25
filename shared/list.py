from collections.abc import Iterable
from typing import Literal

from fabric.utils import Gtk
from fabric.widgets.widget import Widget


def next_batch_size(loaded: int, total: int, batch_size: int) -> int:
    """How many more items a batched list can take this pass.

    Shared by the long lists that are filled a batch at a time (clipboard
    history, notification history, wifi networks): 0 once the list is
    exhausted, otherwise a full or partial batch.
    """
    return max(0, min(batch_size, total - loaded))


def near_list_end(adjustment: Gtk.Adjustment, threshold: int = 50) -> bool:
    """Whether a vertical adjustment is within *threshold* px of its end.

    *threshold* is per-list: the clipboard history prefetches earlier because
    its rows are tall. It must stay positive - GTK3 ignores a scrollbar policy
    of "never", and a zero threshold would mean "already at the end".
    """
    return (
        adjustment.get_value() + adjustment.get_page_size()
        >= adjustment.get_upper() - threshold
    )


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

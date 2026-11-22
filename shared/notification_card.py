"""Shared widget builders for the notification cards.

The toast popup and the date-menu history row render the same anatomy: a header
of icon, summary and trailing controls, plus a body of image and text. The
identical parts live here so both cards stay in sync.
"""

from collections.abc import Callable, Iterable

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from utils.icons import get_text_icon
from utils.widget_utils import nerd_font_icon, resolve_notification_icon

#: Header icon edge length, shared by every card so rows line up.
APP_ICON_SIZE = 20


def app_icon(notification, size: int = APP_ICON_SIZE, **props) -> Image:
    """Return the notification's app icon, sized for a card header.

    Resolution failures yield a pixbuf-less ``Image`` (the default glyph).
    """
    return Image(
        pixbuf=resolve_notification_icon(notification, size),
        size=size,
        v_align="center",
        style_classes="app-icon",
        **props,
    )


def summary_label(markup: str, **props) -> Label:
    """Return the notification summary, the primary label of a header."""
    return Label(
        markup=markup,
        h_align="start",
        h_expand=True,
        line_wrap="word-char",
        style_classes="summary",
        **props,
    )


def timestamp_label(text: str, **props) -> Label:
    """Return a timestamp label pinned to the header's vertical centre."""
    return Label(
        label=str(text),
        v_align="center",
        style_classes="timestamp",
        **props,
    )


def close_button(
    on_clicked: Callable,
    tooltip_text: str | None = None,
    style_classes: Iterable[str] = ("close-button",),
    name: str = "close-button",
    **props,
) -> Button:
    """Return the header's dismiss control.

    *name* is overridable so a control needing its own CSS selector can reuse it.
    """
    return Button(
        name=name,
        v_align="center",
        h_align="center",
        style_classes=list(style_classes),
        tooltip_text=tooltip_text,
        child=nerd_font_icon(
            icon=get_text_icon("ui.window_close", ""),
            props={"style_classes": ["panel-font-icon", "close-icon"]},
        ),
        on_clicked=on_clicked,
        **props,
    )


def header(
    leading: Iterable,
    trailing: Iterable = (),
    spacing: int = 8,
    style_classes: str = "notification-header",
    **props,
) -> Box:
    """Assemble a card header: ``leading`` at the start, ``trailing`` at the end.

    ``trailing`` is in visual order and is packed end back-to-front.
    """
    header_box = Box(
        spacing=spacing,
        orientation="h",
        style_classes=style_classes,
        **props,
    )
    header_box.children = tuple(leading)
    for widget in reversed(tuple(trailing)):
        header_box.pack_end(widget, False, False, 0)
    return header_box

"""Small reusable GTK widgets for the GitHub tray popover.

Every element carries a stable GTK name/style class that
``styles/_github_tray.scss`` targets. No business logic here; data-driven
rendering lives in ``widget.py``.
"""

from __future__ import annotations

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from utils.widget_utils import nerd_font_icon

# fa-brands GitHub mark, used for the bar icon and the avatar fallback.
BRAND_GLYPH = ""


def make_label(
    text: str = "",
    style_classes: str | list[str] | None = None,
    name: str | None = None,
    h_align: str = "start",
    wrap: bool = False,
    max_width: int | None = None,
    lines: int | None = None,
    **kwargs,
) -> Label:
    """A label with the conventions used across the tray UI."""
    classes = ["github-tray-text"]
    if style_classes:
        if isinstance(style_classes, str):
            classes += style_classes.split()
        else:
            classes += list(style_classes)
    label = Label(
        label=text,
        name=name,
        style_classes=classes,
        h_align=h_align,
        line_wrap="word-char" if wrap else "none",
        **kwargs,
    )
    if max_width or not wrap or (wrap and lines):
        if max_width:
            label.set_max_width_chars(max_width)
        label.set_ellipsize(3)
    if lines:
        label.set_lines(lines)
    return label


def make_icon(
    icon: str,
    style_classes: str | list[str] | None = None,
    name: str | None = None,
) -> Label:
    """A Nerd Font glyph label."""
    classes = []
    if style_classes:
        if isinstance(style_classes, str):
            classes += style_classes.split()
        else:
            classes += list(style_classes)
    return nerd_font_icon(icon=icon, name=name, props={"style_classes": classes})


class ActionIconButton(Button):
    """Small square icon button used for card/toolbar actions."""

    def __init__(
        self,
        icon: str,
        tooltip: str | None = None,
        style_classes: str | list[str] | None = None,
        on_clicked=None,
        name: str | None = None,
        **kwargs,
    ):
        classes = ["github-tray-action-btn"]
        if style_classes:
            classes += (
                style_classes.split()
                if isinstance(style_classes, str)
                else list(style_classes)
            )
        options: dict = {}
        if on_clicked is not None:
            options["on_clicked"] = on_clicked
        super().__init__(
            name=name,
            style_classes=classes,
            child=make_icon(icon, style_classes="github-tray-action-icon"),
            tooltip_text=tooltip,
            **options,
            **kwargs,
        )


class Card(Button):
    """A bordered, hoverable card row; nested buttons never get pointer events."""

    def __init__(
        self,
        style_classes: str | list[str] | None = None,
        on_clicked=None,
        name: str | None = None,
        child=None,
        **kwargs,
    ):
        classes = ["github-tray-card"]
        if style_classes:
            classes += (
                style_classes.split()
                if isinstance(style_classes, str)
                else list(style_classes)
            )
        options: dict = {}
        if on_clicked is not None:
            options["on_clicked"] = on_clicked
        super().__init__(
            name=name,
            style_classes=classes,
            child=child or Box(),
            **options,
            **kwargs,
        )


class CardBox(Box):
    """Card chrome as a plain ``Box``; action controls are *siblings*."""

    def __init__(
        self,
        style_classes: str | list[str] | None = None,
        name: str | None = None,
        **kwargs,
    ):
        classes = ["github-tray-card"]
        if style_classes:
            classes += (
                style_classes.split()
                if isinstance(style_classes, str)
                else list(style_classes)
            )
        super().__init__(
            name=name,
            style_classes=classes,
            **kwargs,
        )


class CardMainButton(Button):
    """Transparent full-row button giving a ``CardBox`` its default action."""

    def __init__(
        self,
        on_clicked=None,
        name: str | None = None,
        child=None,
        **kwargs,
    ):
        options: dict = {}
        if on_clicked is not None:
            options["on_clicked"] = on_clicked
        super().__init__(
            name=name,
            style_classes="github-tray-card-main",
            child=child or Box(),
            **options,
            **kwargs,
        )


class Pill(Label):
    """Small rounded status pill (Open / Merged / Failed / language tag ...)."""

    def __init__(
        self,
        text: str = "",
        tint: str | None = None,
        name: str | None = None,
        **kwargs,
    ):
        classes = ["github-tray-pill"]
        if tint:
            classes.append(tint)
        super().__init__(
            label=text,
            name=name,
            style_classes=classes,
            h_align="center",
            **kwargs,
        )


class MetricButton(Button):
    """Clickable metric (stars / forks / issues / PRs) inside a repo card."""

    def __init__(
        self,
        icon: str,
        value: str,
        tooltip: str | None = None,
        tint: str | None = None,
        actionable: bool = True,
        on_clicked=None,
        **kwargs,
    ):
        classes = ["github-tray-metric"]
        if tint:
            classes.append(tint)
        options: dict = {}
        if actionable and on_clicked is not None:
            classes.append("actionable")
            options["on_clicked"] = on_clicked
        super().__init__(
            style_classes=classes,
            tooltip_text=tooltip if actionable else None,
            child=Box(
                spacing=4,
                children=[
                    make_icon(icon, style_classes="github-tray-metric-icon"),
                    make_label(value, style_classes=["github-tray-metric-value"]),
                ],
            ),
            **options,
            **kwargs,
        )


class EmptyState(Box):
    """Centered empty/onboarding state with icon + title + subtitle."""

    def __init__(
        self,
        icon: str,
        title: str,
        subtitle: str = "",
        **kwargs,
    ):
        children: list = [
            make_icon(
                icon,
                style_classes=["github-tray-empty-icon"],
                name="github-tray-empty-icon",
            ),
            make_label(
                title,
                style_classes=["github-tray-empty-title"],
                h_align="center",
                wrap=True,
            ),
        ]
        if subtitle:
            children.append(
                make_label(
                    subtitle,
                    style_classes=["github-tray-empty-subtitle"],
                    h_align="center",
                    wrap=True,
                )
            )
        super().__init__(
            orientation="v",
            spacing=6,
            style_classes=["github-tray-empty"],
            h_align="center",
            children=children,
            **kwargs,
        )


class SkeletonRow(Box):
    """Pulsing placeholder rows shown while the first load is in flight."""

    def __init__(self, rows: int = 4, **kwargs):
        bars = [
            make_label(
                "█" * (34 - (index % 3) * 7),
                style_classes="github-tray-skeleton-bar",
            )
            for index in range(rows)
        ]
        super().__init__(
            orientation="v",
            spacing=10,
            style_classes=["github-tray-skeleton"],
            children=bars,
            **kwargs,
        )


class SectionLabel(Label):
    """All-caps section heading (UNREAD / REPOSITORIES / detail titles)."""

    def __init__(self, text: str, name: str | None = None, **kwargs):
        super().__init__(
            label=text,
            name=name,
            style_classes="github-tray-section-label",
            h_align="start",
            **kwargs,
        )


def vbox(
    spacing: int = 8, name: str | None = None, style_classes=None, **kwargs
) -> Box:
    return Box(
        orientation="v",
        spacing=spacing,
        name=name,
        style_classes=style_classes or [],
        **kwargs,
    )


def hbox(
    spacing: int = 8, name: str | None = None, style_classes=None, **kwargs
) -> Box:
    return Box(
        orientation="h",
        spacing=spacing,
        name=name,
        style_classes=style_classes or [],
        **kwargs,
    )

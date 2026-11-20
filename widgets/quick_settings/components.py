from collections.abc import Callable
from typing import Literal

from fabric.widgets.box import Box
from fabric.widgets.label import Label

from utils.widget_utils import nerd_font_icon


class QuickSettingsIconLabelRow(Box):
    """Reusable icon + label row used across quick settings widgets."""

    def __init__(
        self,
        icon: str,
        label: str,
        subtitle: str | None = None,
        icon_classes: list[str] | None = None,
        label_classes: list[str] | None = None,
        row_classes: list[str] | None = None,
        icon_size: int = 16,
        h_align: Literal["start", "fill", "center", "end", "baseline"] = "start",
        **kwargs,
    ):
        self.icon = nerd_font_icon(
            icon=icon,
            props={
                "style_classes": ["panel-font-icon", "quicksettings-row-icon"]
                + (icon_classes or []),
                "style": f"font-size: {icon_size}px;",
            },
        )

        self.label = Label(
            label=label,
            h_align="start",
            h_expand=True,
            ellipsization="end",
            style_classes=["panel-text", "quicksettings-row-label"]
            + (label_classes or []),
        )

        self.subtitle: Label | None = None
        text_children = (self.label,)
        if subtitle is not None:
            self.subtitle = Label(
                label=subtitle,
                h_align="start",
                h_expand=True,
                ellipsization="end",
                style_classes=["panel-text", "quicksettings-row-subtitle"]
                + (label_classes or []),
            )
            text_children = (
                Box(
                    orientation="v",
                    v_align="center",
                    h_expand=True,
                    children=(self.label, self.subtitle),
                ),
            )

        super().__init__(
            orientation="h",
            spacing=10,
            h_align=h_align,
            v_align="center",
            style_classes=["quicksettings-row"] + (row_classes or []),
            children=(self.icon, *text_children),
            **kwargs,
        )


class LazyWidgetContainer(Box):
    """Build child widget on first map to avoid eager initialization costs."""

    def __init__(self, factory: Callable[[], object], **kwargs):
        super().__init__(**kwargs)
        self._factory = factory
        self._is_loaded = False
        self.connect("map", self._ensure_loaded)

    def _ensure_loaded(self, *_):
        if self._is_loaded:
            return

        child = self._factory()
        if child is None:
            return

        self.children = (child,)
        self._is_loaded = True

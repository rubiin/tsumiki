"""Shared base widget for quick-setting toggle tiles in the Quick Settings popover.

Every tile renders an icon + optional label + optional subtitle side by side
inside a single ``QuickSettingsIconLabelRow``.  State updates are driven by
``set_state`` so unchanged refreshes never churn the DOM, and the widget
tracks its signal handlers so ``destroy`` cleans everything up safely.
"""

from typing import Optional

from shared.buttons import HoverButton
from widgets.quick_settings.components import QuickSettingsIconLabelRow


class QuickSettingToggle(HoverButton):
    """A reusable card toggle for quick settings popover tiles.

    Parameters
    ----------
    popup:
        Popup widget to close when the toggle is activated.
    icon:
        Icon text for the left-side symbol (symbolic icon name).
    title:
        Title label shown above the icon/status pair.
    subtitle:
        Status label below the icon (e.g. ``"off"`` / ``"on"``).
    """

    def __init__(
        self, popup, icon: str, title: str, subtitle: str | None = None, **kwargs
    ):
        super().__init__(
            name="quicksettings-togglebutton",
            style_classes="quicksettings-toggler",
            popup=popup,
            **kwargs,
        )

        self.popup = popup
        self.row = QuickSettingsIconLabelRow(
            icon=icon,
            label=title,
            subtitle=subtitle,
            icon_size=20,
            row_classes=["quicksettings-toggle-row"],
            h_align="fill",
        )
        self.icon_label = self.row.icon
        self.status_label = self.row.subtitle
        self.children = self.row

        self._active = False
        self._last_icon: Optional[str] = None
        self._last_status: Optional[str] = None

        self.connect("clicked", self._on_clicked)

    # ── Click handling ────────────────────────────────────────────────

    def _on_clicked(self, *_):
        """Hide the popover when the toggle is activated."""
        if self.popup is not None:
            self.popup.hide_popover()

    def on_click(self, *_):
        """Subclasses must implement this to perform the actual toggle."""
        raise NotImplementedError

    def set_state(
        self,
        active: bool,
        icon: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        """Update the visual state of the tile.

        Only touches the label text when the value actually changes, keeping
        redraws cheap even when the underlying service state flips back and forth.
        """
        self._active = bool(active)
        self.toggle_css_class("active", bool(active))

        if icon is not None and icon != self._last_icon:
            self.icon_label.set_label(icon)
            self._last_icon = icon

        if (
            status is not None
            and self.status_label is not None
            and status != self._last_status
        ):
            self.status_label.set_label(status)
            self._last_status = status

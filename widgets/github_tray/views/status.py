"""Error and onboarding states for the GitHub tray popover."""

from __future__ import annotations

from fabric.widgets.box import Box

from .. import state as tray_state
from ..components import (
    ActionIconButton,
    CardBox,
    EmptyState,
    hbox,
    make_icon,
    make_label,
)


class StatusView:
    """Mixin: the banner above the lists (API failure or no ``gh auth`` yet)."""

    def _build_status(self) -> Box | None:
        widget = self.tray_widget
        if widget.error_message:
            card = CardBox(
                name="github-tray-error",
                style_classes="github-tray-error-card",
                orientation="v",
                spacing=6,
                children=[
                    hbox(
                        spacing=8,
                        children=[
                            make_icon(
                                tray_state.glyph("error"),
                                style_classes="github-tray-error-icon",
                            ),
                            make_label(
                                "Could not reach GitHub",
                                style_classes="github-tray-error-title",
                            ),
                        ],
                    ),
                    make_label(
                        widget.error_message,
                        style_classes="github-tray-error-message",
                        wrap=True,
                    ),
                    hbox(
                        spacing=6,
                        children=[
                            # Chrome box, not a Button: these must stay clickable.
                            self._refresh_button("Retry"),
                            ActionIconButton(
                                icon=tray_state.glyph("open_link"),
                                tooltip="Open github.com",
                                on_clicked=lambda *_: widget.open_web(),
                            ),
                        ],
                    ),
                ],
            )
            card.set_tooltip_text(widget.error_message)
            return card

        if not widget.user and not widget.loaded_once and not widget.loading:
            return EmptyState(
                icon=tray_state.glyph("github"),
                title="GitHub Tray",
                subtitle=(
                    "Login with `gh auth login` to show your\n"
                    "notifications, repositories and Actions here."
                ),
            )
        return None

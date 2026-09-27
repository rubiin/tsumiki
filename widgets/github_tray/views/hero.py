"""Profile header (avatar, name, chips) for the GitHub tray popover."""

from __future__ import annotations

from fabric.widgets.box import Box

from shared.circle_image import CircularImage

from .. import state as tray_state
from ..components import (
    BRAND_GLYPH,
    ActionIconButton,
    hbox,
    make_icon,
    make_label,
    vbox,
)


class HeroView:
    """Mixin: the avatar + name + counters row, and the widget's actions."""

    def _build_hero(self) -> Box:
        widget = self.tray_widget
        user = widget.user or {}
        login = str(user.get("login") or "") or str(self.config.get("username", ""))

        avatar = Box(
            name="github-tray-avatar-box",
            style_classes="github-tray-avatar-box",
            size_request=(int(self.config.get("avatar_size", 44)),) * 2,
        )
        if widget.avatar_pixbuf is not None:
            avatar.children = [
                CircularImage(
                    pixbuf=widget.avatar_pixbuf,
                    size=int(self.config.get("avatar_size", 44)),
                    name="github-tray-avatar",
                )
            ]
        else:
            avatar.children = [
                Box(
                    name="github-tray-avatar-fallback",
                    style_classes="github-tray-avatar-fallback",
                    h_align="center",
                    v_align="center",
                    children=[
                        make_icon(
                            BRAND_GLYPH,
                            style_classes="github-tray-avatar-fallback-icon",
                        )
                    ],
                )
            ]

        name_col = vbox(
            spacing=2,
            h_expand=True,
            children=[
                make_label(
                    login or "GitHub",
                    style_classes="github-tray-name",
                    max_width=20,
                ),
                hbox(
                    spacing=6,
                    children=self._build_chips(),
                ),
            ],
        )

        actions = hbox(
            spacing=2,
            children=[
                self._refresh_button(),
                ActionIconButton(
                    icon=tray_state.glyph("open_link"),
                    tooltip="Open github.com",
                    on_clicked=lambda *_: widget.open_web(),
                ),
            ],
        )

        return hbox(
            spacing=10,
            name="github-tray-hero",
            style_classes="github-tray-hero",
            children=[avatar, name_col, actions],
        )

    def _build_chips(self) -> list:
        widget = self.tray_widget
        user = widget.user or {}
        total_stars = sum(r.get("stargazers_count") or 0 for r in widget.repos)
        chips = [
            (
                tray_state.glyph("account"),
                tray_state.format_count(user.get("followers")),
                "Followers",
            ),
            (
                tray_state.glyph("repo"),
                tray_state.format_count(user.get("public_repos")),
                "Repositories",
            ),
            (
                tray_state.glyph("star"),
                tray_state.format_count(total_stars),
                "Stars",
            ),
        ]
        built = []
        for icon, value, tooltip in chips:
            box = hbox(
                spacing=3,
                style_classes="github-tray-chip",
                children=[
                    make_icon(icon, style_classes="github-tray-chip-icon"),
                    make_label(value, style_classes="github-tray-chip-value"),
                ],
            )
            box.set_tooltip_text(tooltip)
            built.append(box)
        return built

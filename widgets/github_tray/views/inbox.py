"""Unread-notification inbox for the GitHub tray popover."""

from __future__ import annotations

from fabric.widgets.box import Box

from .. import state as tray_state
from ..components import (
    ActionIconButton,
    CardBox,
    CardMainButton,
    EmptyState,
    Pill,
    SectionLabel,
    hbox,
    make_icon,
    make_label,
    vbox,
)

PAGE_SIZE = 8


class InboxView:
    """Mixin: the UNREAD list, its cards and its pager."""

    def _build_inbox(self) -> Box:
        widget = self.tray_widget
        notifications = list(widget.notifications)
        notification_key = tuple(str(n.get("id")) for n in notifications)
        if notification_key != self._last_notification_key:
            self._last_notification_key = notification_key
            self._notify_page = 0

        header = hbox(
            children=[
                SectionLabel("UNREAD"),
                Box(h_expand=True),
                ActionIconButton(
                    icon=tray_state.glyph("open_link"),
                    tooltip="Open inbox on GitHub",
                    on_clicked=lambda *_: widget.open_url(
                        f"{widget.web_base}/notifications"
                    ),
                ),
            ],
        )
        pieces: list = [header]

        if not notifications:
            pieces.append(
                EmptyState(
                    icon=tray_state.glyph("bell"),
                    title="You're all caught up",
                    subtitle="No unread notifications",
                )
            )
        else:
            start = self._notify_page * PAGE_SIZE
            page = notifications[start : start + PAGE_SIZE]
            pieces.extend(self._build_notification_cards(page))
            pieces.append(self._build_pager(len(notifications)))

        return vbox(spacing=8, name="github-tray-inbox", children=pieces)

    def _build_notification_cards(self, page: list[dict]) -> list:
        widget = self.tray_widget
        cards = []
        for item in page:
            subject = item.get("subject") or {}
            repo = item.get("repository") or {}
            state = tray_state.notification_state(item)
            # Chrome box: the text row and mark-as-read button are separate targets.
            cards.append(
                CardBox(
                    name="github-tray-notification",
                    style_classes="github-tray-notification-card",
                    orientation="h",
                    spacing=8,
                    children=[
                        CardMainButton(
                            h_expand=True,
                            on_clicked=lambda *_, _i=item: widget.mark_read(
                                _i, open_after=True
                            ),
                            child=self._notification_text_row(
                                item, subject, repo, state
                            ),
                        ),
                        ActionIconButton(
                            icon=tray_state.glyph("check"),
                            tooltip="Mark as read",
                            style_classes="github-tray-mark-btn",
                            on_clicked=lambda *_, _i=item: widget.mark_read(_i),
                        ),
                    ],
                )
            )
            if str(item.get("id")) == widget.pending_notification_id:
                cards[-1].add_style_class("busy")
        return cards

    def _notification_text_row(
        self, item: dict, subject: dict, repo: dict, state: str
    ) -> Box:
        return hbox(
            spacing=8,
            children=[
                make_icon(
                    tray_state.notification_icon(item),
                    style_classes="github-tray-notification-icon",
                ),
                vbox(
                    spacing=2,
                    h_expand=True,
                    children=[
                        make_label(
                            str(subject.get("title") or "Untitled"),
                            style_classes="github-tray-notification-title",
                            wrap=True,
                            lines=2,
                        ),
                        hbox(
                            spacing=6,
                            children=[
                                make_label(
                                    str(repo.get("full_name") or ""),
                                    style_classes="github-tray-notification-repo",
                                    max_width=18,
                                ),
                                Pill(text=state) if state else Box(),
                                make_label(
                                    tray_state.reason_label(item.get("reason")),
                                    style_classes="github-tray-notification-meta",
                                    max_width=16,
                                ),
                                Box(h_expand=True),
                                make_label(
                                    tray_state.relative_time(item.get("updated_at")),
                                    style_classes="github-tray-notification-meta",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )

    def _build_pager(self, total: int) -> Box:
        if total <= PAGE_SIZE:
            return Box()
        pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
        page = self._notify_page

        def go(delta):
            self._notify_page = max(0, min(pages - 1, page + delta))
            self._render()

        return hbox(
            spacing=8,
            name="github-tray-pager",
            style_classes="github-tray-pager",
            children=[
                Box(h_expand=True),
                ActionIconButton(
                    icon=tray_state.glyph("back"),
                    tooltip="Previous page",
                    on_clicked=lambda *_: go(-1),
                ),
                make_label(
                    f"{page + 1} / {pages}", style_classes="github-tray-pager-label"
                ),
                ActionIconButton(
                    icon=tray_state.glyph("forward"),
                    tooltip="Next page",
                    on_clicked=lambda *_: go(+1),
                ),
                Box(h_expand=True),
            ],
        )

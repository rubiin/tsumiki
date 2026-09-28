"""Per-repo detail views (issues, pull requests, workflow runs)."""

from __future__ import annotations

from fabric.widgets.box import Box

from .. import state as tray_state
from ..components import (
    ActionIconButton,
    Card,
    CardBox,
    CardMainButton,
    EmptyState,
    Pill,
    SkeletonRow,
    hbox,
    make_icon,
    make_label,
    vbox,
)

_TITLES = {"issues": "Issues", "pulls": "Pull Requests", "workflows": "Workflow Runs"}
_EMPTY = {
    "issues": "No open issues",
    "pulls": "No open pull requests",
    "workflows": "No workflow runs",
}


class DetailView:
    """Mixin: the drill-down views for one repository."""

    def _render_detail(self) -> list:
        widget = self.tray_widget
        detail = widget.detail
        repo = detail.get("repo") or {}
        kind = detail.get("kind") or "issues"

        header = hbox(
            spacing=8,
            children=[
                ActionIconButton(
                    icon=tray_state.glyph("back"),
                    tooltip="Back",
                    on_clicked=lambda *_: self._back_to_main(),
                ),
                vbox(
                    spacing=0,
                    h_expand=True,
                    children=[
                        make_label(
                            _TITLES.get(kind, "GitHub"),
                            style_classes="github-tray-detail-title",
                        ),
                        make_label(
                            str(repo.get("full_name") or ""),
                            style_classes="github-tray-detail-subtitle",
                            max_width=28,
                        ),
                    ],
                ),
                ActionIconButton(
                    icon=tray_state.glyph("open_link"),
                    tooltip="Open on GitHub",
                    on_clicked=lambda *_: widget.open_url(
                        self._detail_browser_url(repo, kind)
                    ),
                ),
            ],
        )
        pieces: list = [header]

        if detail.get("pending"):
            pieces.append(SkeletonRow(rows=3))
            return vbox(spacing=8, children=pieces)

        error = str(detail.get("error") or "")
        if error:
            # Without this a failed `gh` call reads as "nothing to show".
            pieces.append(
                EmptyState(
                    icon=tray_state.glyph("error"),
                    title="Could not load",
                    subtitle=error,
                )
            )
            return vbox(spacing=8, children=pieces)

        items = detail.get("items") or []
        if not items:
            pieces.append(
                EmptyState(
                    icon=tray_state.glyph("repo"),
                    title=_EMPTY.get(kind, ""),
                    subtitle="",
                )
            )
            return vbox(spacing=8, children=pieces)

        if kind == "workflows":
            pieces.extend(self._build_run_cards(items))
        else:
            pieces.extend(self._build_item_cards(items, kind))
        return vbox(spacing=8, children=pieces)

    def _detail_browser_url(self, repo: dict, kind: str) -> str:
        base = str(repo.get("html_url") or self.tray_widget.web_base)
        suffix = {
            "issues": "/issues",
            "pulls": "/pulls",
            "workflows": "/actions",
        }.get(kind, "")
        return base + suffix

    def _build_item_cards(self, items: list[dict], kind: str) -> list:
        widget = self.tray_widget
        cards = []
        for item in items:
            number = str(item.get("number") or "")
            labels = (item.get("labels") or [])[:6]
            author = (item.get("user") or {}).get("login") or ""
            meta = " · ".join(
                part
                for part in [
                    f"@{author}" if author else "",
                    tray_state.relative_time(item.get("updated_at")),
                ]
                if part
            )
            label_row = None
            if labels:
                label_row = hbox(
                    spacing=4,
                    children=[
                        Pill(
                            text=str(label.get("name") or ""),
                            tint=None,
                        )
                        for label in labels
                    ],
                )
            title = str(item.get("title") or "Untitled")
            content = vbox(
                spacing=3,
                children=[
                    hbox(
                        spacing=6,
                        children=[
                            make_label(
                                f"#{number}",
                                style_classes="github-tray-detail-number",
                            ),
                            make_label(
                                title,
                                style_classes="github-tray-detail-item-title",
                                wrap=True,
                                lines=2,
                                h_expand=True,
                            ),
                        ],
                    ),
                    hbox(
                        spacing=6,
                        children=[
                            Pill(text="Draft") if item.get("draft") else Box(),
                            make_label(
                                meta,
                                style_classes="github-tray-detail-meta",
                                max_width=30,
                            ),
                        ],
                    ),
                    *([label_row] if label_row else []),
                ],
            )
            cards.append(
                Card(
                    name="github-tray-detail-item",
                    style_classes="github-tray-detail-card",
                    on_clicked=lambda *_, _i=item: (
                        widget.open_url(_i.get("html_url")),
                        widget.hide_popover(),
                    ),
                    child=content,
                )
            )
        return cards

    def _build_run_cards(self, runs: list[dict]) -> list:
        widget = self.tray_widget
        cards = []
        for run in runs:
            status = tray_state.workflow_status(run)
            duration = tray_state.workflow_duration(run)
            branch = str(run.get("head_branch") or "")
            meta_parts = [
                str(run.get("name") or ""),
                f"⎇ {branch}" if branch else "",
                f"󰔟 {duration}" if duration else "",
                tray_state.relative_time(run.get("updated_at")),
            ]
            meta = "  ·  ".join(p for p in meta_parts if p)
            can_rerun = run.get("status") == "completed" and run.get("conclusion") in (
                "failure",
                "cancelled",
                "timed_out",
            )
            run_tint = tray_state.run_tint(run)

            def _open_run(*_, _r=run):
                widget.open_url(_r.get("html_url"))
                widget.hide_popover()

            # Chrome box, not a Button: the re-run button must stay a clickable sibling.
            cards.append(
                CardBox(
                    name="github-tray-run",
                    style_classes="github-tray-detail-card",
                    orientation="v",
                    spacing=3,
                    children=[
                        CardMainButton(
                            h_expand=True,
                            on_clicked=_open_run,
                            child=hbox(
                                spacing=6,
                                children=[
                                    make_icon(
                                        tray_state.workflow_icon(run),
                                        style_classes=(
                                            ["github-tray-run-icon", run_tint]
                                            if run_tint
                                            else "github-tray-run-icon"
                                        ),
                                    ),
                                    make_label(
                                        str(
                                            run.get("display_title")
                                            or run.get("name")
                                            or "Workflow"
                                        ),
                                        style_classes="github-tray-run-title",
                                        wrap=True,
                                        lines=2,
                                        h_expand=True,
                                    ),
                                ],
                            ),
                        ),
                        hbox(
                            spacing=6,
                            children=[
                                CardMainButton(
                                    h_expand=True,
                                    on_clicked=_open_run,
                                    child=hbox(
                                        spacing=6,
                                        children=[
                                            Pill(text=status),
                                            make_label(
                                                meta,
                                                style_classes="github-tray-detail-meta",
                                                max_width=40,
                                                h_expand=True,
                                            ),
                                        ],
                                    ),
                                ),
                                ActionIconButton(
                                    icon=tray_state.glyph("refresh"),
                                    tooltip="Re-run failed jobs",
                                    on_clicked=lambda *_, _r=run: widget.rerun(_r),
                                    visible=can_rerun,
                                ),
                            ],
                        ),
                    ],
                )
            )
        return cards

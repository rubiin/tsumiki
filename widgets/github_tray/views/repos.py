"""Repository list for the GitHub tray popover."""

from __future__ import annotations

from fabric.widgets.box import Box

from .. import state as tray_state
from ..components import (
    ActionIconButton,
    CardBox,
    CardMainButton,
    EmptyState,
    MetricButton,
    SectionLabel,
    hbox,
    make_icon,
    make_label,
    vbox,
)


class ReposView:
    """Mixin: the REPOSITORIES list and one card per repo."""

    def _build_repos(self) -> Box:
        widget = self.tray_widget
        repos = tray_state.sort_repos(
            widget.repos,
            str(self.config.get("sort_by", "updated")),
            str(self.config.get("sort_order", "desc")),
            int(self.config.get("max_repos", 10)),
        )
        header = hbox(
            children=[
                SectionLabel("REPOSITORIES"),
                make_label(
                    tray_state.sort_label(
                        str(self.config.get("sort_by", "updated")),
                        str(self.config.get("sort_order", "desc")),
                    ),
                    style_classes="github-tray-sort-label",
                ),
                Box(h_expand=True),
                ActionIconButton(
                    icon=tray_state.glyph("open_link"),
                    tooltip="View all repositories",
                    on_clicked=lambda *_: widget.open_url(
                        f"{widget.web_base}/"
                        f"{widget.user.get('login', '')}?tab=repositories"
                    ),
                ),
            ],
        )
        pieces: list = [header]
        if not repos:
            pieces.append(
                EmptyState(
                    icon=tray_state.glyph("repo"),
                    title="No repositories",
                    subtitle="Nothing matched your filters",
                )
            )
        else:
            username = str(widget.user.get("login") or "")
            pieces.extend(self._build_repo_cards(repos, username))
        return vbox(spacing=8, name="github-tray-repos", children=pieces)

    def _build_repo_cards(self, repos: list[dict], username: str) -> list:
        widget = self.tray_widget
        cards = []
        for repo in repos:
            full_name = str(repo.get("full_name") or "")
            owner_login = str((repo.get("owner") or {}).get("login") or "")
            is_own = (not owner_login) or owner_login == username
            name_text = (
                repo.get("name") if is_own else f"{owner_login}/{repo.get('name')}"
            )
            icon = (
                tray_state.glyph("fork")
                if repo.get("fork")
                else tray_state.glyph("lock")
                if repo.get("private")
                else tray_state.glyph("repo")
            )
            language = str(repo.get("language") or "")
            metrics = [
                # Read-only metrics: actionable=False drops the misleading affordance.
                MetricButton(
                    icon=tray_state.glyph("star"),
                    value=tray_state.format_count(repo.get("stargazers_count")),
                    tooltip="Stars",
                    tint="warning",
                    actionable=False,
                ),
                MetricButton(
                    icon=tray_state.glyph("fork"),
                    value=tray_state.format_count(repo.get("forks_count")),
                    tooltip="Forks",
                    actionable=False,
                ),
                MetricButton(
                    icon=tray_state.glyph("issue"),
                    value=tray_state.format_count(repo.get("_issuesCount")),
                    tooltip="Open issues",
                    tint="success",
                    on_clicked=lambda *_, _r=repo: widget.load_details(_r, "issues"),
                ),
                MetricButton(
                    icon=tray_state.glyph("pull"),
                    value=tray_state.format_count(repo.get("_pullsCount")),
                    tooltip="Open pull requests",
                    tint="accent",
                    on_clicked=lambda *_, _r=repo: widget.load_details(_r, "pulls"),
                ),
            ]
            actions = [
                ActionIconButton(
                    icon=tray_state.glyph("play"),
                    tooltip="Workflow runs",
                    on_clicked=lambda *_, _r=repo: widget.load_details(_r, "workflows"),
                ),
                ActionIconButton(
                    icon=tray_state.glyph("open_link"),
                    tooltip="Open on GitHub",
                    on_clicked=lambda *_, _r=repo: (
                        widget.open_url(_r.get("html_url")),
                        widget.hide_popover(),
                    ),
                ),
            ]
            local = widget.repo_local_path(repo)
            if local:
                actions.append(
                    ActionIconButton(
                        icon=tray_state.glyph("folder_open"),
                        tooltip=f"Open in {widget.editor_command()}\n{local}",
                        on_clicked=lambda *_, _r=repo: widget.open_repo(_r),
                    )
                )

            top_row = hbox(
                spacing=6,
                children=[
                    make_icon(icon, style_classes="github-tray-repo-icon"),
                    make_label(
                        name_text,
                        style_classes="github-tray-repo-name",
                        max_width=24,
                    ),
                    make_label(
                        language,
                        style_classes="github-tray-repo-language",
                    ),
                    Box(h_expand=True),
                    make_label(
                        tray_state.relative_time(
                            repo.get("pushed_at") or repo.get("updated_at")
                        ),
                        style_classes="github-tray-repo-age",
                    ),
                ],
            )
            desc_row = None
            description = str(repo.get("description") or "")
            if description:
                desc_row = make_label(
                    description,
                    style_classes="github-tray-repo-description",
                    wrap=True,
                    lines=2,
                )

            # Chrome box, not a Button: metrics and action icons must stay clickable.
            card = CardBox(
                name="github-tray-repo",
                style_classes="github-tray-repo-card",
                orientation="v",
                spacing=2,
                children=[
                    CardMainButton(
                        on_clicked=lambda *_, _r=repo: widget.open_repo(_r),
                        child=vbox(
                            spacing=2,
                            children=[
                                top_row,
                                *([desc_row] if desc_row else []),
                            ],
                        ),
                    ),
                    hbox(
                        spacing=2,
                        children=[*metrics, Box(h_expand=True), *actions],
                    ),
                ],
            )
            card.set_tooltip_text(str(repo.get("html_url") or full_name))
            cards.append(card)
        return cards

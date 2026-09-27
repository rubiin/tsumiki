"""Popover content for the GitHub tray: chrome, tabs and view dispatch.

The section builders live in :mod:`widgets.github_tray.views` as mixins; this
class owns the scroller, the tab strip, the render memo and the navigation.
"""

from __future__ import annotations

from time import monotonic

from fabric.utils import GLib
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

from . import state as tray_state
from .components import ActionIconButton, Card, SkeletonRow, hbox, make_icon, make_label
from .views import DetailView, HeroView, InboxView, ReposView, StatusView


class GitHubTrayPopoverContent(
    HeroView, StatusView, InboxView, ReposView, DetailView, Box
):
    """Popover content: hero, tabs, lists, detail views, toasts."""

    def __init__(self, widget, **kwargs):
        super().__init__(
            name="github-tray-window",
            orientation="v",
            spacing=10,
            style_classes="github-tray-window",
            **kwargs,
        )
        self.tray_widget = widget
        self.config = widget.config

        self._view = "main"  # main | issues | pulls | workflows | error
        self._tab = self._normalize_tab(str(self.config.get("default_tab", "inbox")))
        self._notify_page = 0
        self._last_notification_key: tuple = ()
        self._last_render_key: tuple | None = None
        self._toast_timer: int | None = None

        self._body = ScrolledWindow(
            name="github-tray-scroller",
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
        )
        self._body.set_min_content_width(360)
        self._body.set_min_content_height(480)

        self._stack = Box(
            orientation="v",
            spacing=10,
            name="github-tray-items",
            style_classes="github-tray-items",
        )
        self._body.add(self._stack)

        self.toast_label = Label(
            label="",
            name="github-tray-toast",
            style_classes="github-tray-toast",
            h_align="center",
            visible=False,
        )

        self.children = [self._body, self.toast_label]

        self.tray_widget_draw_count = 0
        self._render()
        self.show_all()
        self.toast_label.set_visible(False)

    # -- tab helpers --
    @staticmethod
    def _normalize_tab(tab: str) -> str:
        return tab if tab in ("inbox", "repos") else "inbox"

    def set_tab(self, tab: str):
        self._tab = self._normalize_tab(tab)
        self._render()

    @property
    def effective_tab(self) -> str:
        if not self.tray_widget.config.get("show_notifications", True):
            return "repos"
        return self._tab

    def _refresh_button(self, tooltip: str = "Refresh"):
        """The refresh action; it turns into a spinner while a fetch is in flight."""
        widget = self.tray_widget
        icon, classes = tray_state.refresh_button_spec(bool(widget.loading))
        return ActionIconButton(
            icon=icon,
            tooltip=tooltip,
            style_classes=classes,
            on_clicked=lambda *_: widget.refresh(manual=True),
        )

    # -- rendering --
    def on_widget_data_changed(self):
        """Re-render whatever changed; cheap full rebuild for the tray."""
        detail_kind = self.tray_widget.detail.get("kind")
        if detail_kind and self._view == "main":
            self._view = detail_kind
        elif not detail_kind and self._view != "main":
            self._view = "main"
        self._render()

    def invalidate_render_cache(self):
        """Force the next render to rebuild, e.g. when the popover becomes visible."""
        self._last_render_key = None

    def show_toast(self, message: str):
        self.toast_label.set_label(f"󰄬  {message}")
        self.toast_label.set_visible(True)
        if self._toast_timer is not None:
            GLib.source_remove(self._toast_timer)
        self._toast_timer = GLib.timeout_add(2200, self._hide_toast)

    def _hide_toast(self):
        self._toast_timer = None
        self.toast_label.set_visible(False)
        return False

    def _render_key(self) -> tuple | None:
        """Inputs that decide the main-view output; ``None`` disables memoisation."""
        widget = self.tray_widget
        if self._view != "main":
            return None
        notifications = tuple(
            (
                str(item.get("id")),
                tray_state.notification_state(item),
                str(item.get("reason")),
                str(item.get("updated_at")),
                str((item.get("subject") or {}).get("title")),
                str((item.get("repository") or {}).get("full_name")),
                str(item.get("id")) == widget.pending_notification_id,
            )
            for item in widget.notifications
        )
        repos = tuple(
            (
                str(repo.get("full_name")),
                repo.get("stargazers_count"),
                repo.get("forks_count"),
                repo.get("_issuesCount"),
                repo.get("_pullsCount"),
                str(repo.get("pushed_at") or repo.get("updated_at")),
            )
            for repo in widget.repos
        )
        return (
            self._view,
            self._tab,
            self._notify_page,
            # Bucket the clock so "5m ago" labels refresh during a long-open popover.
            int(monotonic() // 300),
            widget.loading,
            widget.loaded_once,
            widget.error_message,
            widget.avatar_pixbuf is not None,
            widget.web_base,
            tuple(sorted((str(k), str(v)) for k, v in (widget.user or {}).items())),
            notifications,
            repos,
        )

    def _render(self):
        key = self._render_key()
        if key is not None and key == self._last_render_key:
            return

        self.tray_widget_draw_count += 1

        children: list = []
        if self._view == "main":
            children = self._render_main()
        else:
            children = self._render_detail()
        self._stack.children = children
        self._stack.show_all()
        self._last_render_key = key

    # -- main view --
    def _render_main(self) -> list:
        widget = self.tray_widget
        pieces: list = []

        if widget.loaded_once or widget.error_message:
            pieces.append(self._build_hero())
            status = self._build_status()
            if status is not None:
                pieces.append(status)

        if widget.loading and not widget.loaded_once and not widget.error_message:
            pieces.append(SkeletonRow(rows=4))

        if widget.loaded_once and not widget.error_message:
            if widget.config.get("show_notifications", True):
                pieces.append(self._build_tabs())
            pieces.append(self._build_tab_content())
        return pieces

    def _build_tabs(self) -> Box:
        widget = self.tray_widget
        return hbox(
            spacing=4,
            name="github-tray-tabs",
            style_classes="github-tray-tabs",
            children=[
                self._make_tab_button("inbox", "󰂚", "Inbox", widget.unread_count),
                self._make_tab_button(
                    "repos", tray_state.glyph("repo"), "Repositories", len(widget.repos)
                ),
            ],
        )

    def _make_tab_button(self, tab: str, icon: str, label: str, count: int) -> Box:
        count_label = make_label(
            f"{count}" if count else "",
            style_classes="github-tray-tab-count",
            h_align="center",
        )
        count_label.set_visible(bool(count))
        button = Card(
            name=f"github-tray-tab-{tab}",
            style_classes="github-tray-tab-btn",
            on_clicked=lambda *_: self.set_tab(tab),
            child=hbox(
                spacing=6,
                children=[
                    make_icon(icon, style_classes="github-tray-tab-icon"),
                    make_label(label, style_classes="github-tray-tab-label"),
                    count_label,
                ],
            ),
        )
        button.set_h_expand(True)
        if self.effective_tab == tab:
            button.add_style_class("active")
        return button

    def _build_tab_content(self) -> Box:
        if self.effective_tab == "inbox":
            return self._build_inbox()
        return self._build_repos()

    # -- navigation --
    def _back_to_main(self):
        widget = self.tray_widget
        widget.detail = {
            "kind": None,
            "repo": None,
            "items": [],
            "pending": False,
        }
        self._view = "main"
        self._render()

    def show_detail(self, kind: str):
        self._view = "main"
        widget = self.tray_widget
        if widget.detail.get("kind") == kind:
            self._view = kind
        self._render()

    def close(self, *_):
        if self.tray_widget.popup is not None:
            self.tray_widget.hide_popover()

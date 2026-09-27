"""GitHub tray bar button + popover.

Mirrors the Omarchy "github-tray" panel (notifications, repositories, per-repo
issues/PRs/Actions, alerts, local-project mappings) inside a Tsumiki bar
widget. All data comes from the ``gh`` CLI; the widget relies on the user's
``gh auth`` session.
"""

from __future__ import annotations

import json
import shlex
from contextlib import suppress
from time import monotonic

from fabric.utils import GLib, idle_add
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

import utils.functions as helpers
from shared.circle_image import CircularImage
from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget
from utils.constants import APP_DATA_DIRECTORY
from utils.functions import get_http_client, send_notification
from utils.i18n import _
from utils.widget_utils import nerd_font_icon

from . import state as tray_state
from .client import GitHubClient, GitHubClientError
from .components import (
    ActionIconButton,
    Card,
    CardBox,
    CardMainButton,
    EmptyState,
    MetricButton,
    Pill,
    SectionLabel,
    SkeletonRow,
    hbox,
    make_icon,
    make_label,
    vbox,
)

STATE_FILE = f"{APP_DATA_DIRECTORY}/github_tray_state.json"
MENU_CACHE_FILE = f"{APP_DATA_DIRECTORY}/github_tray_menu_cache.json"
PAGE_SIZE = 8
# In-memory throttle used when the disk cache is disabled (``cache_ttl = 0``).
REPOS_REFRESH_SECONDS = 300
DEFAULT_CACHE_TTL = 3600
MIN_NOTIFY_INTERVAL = 30

_GLYPH_BRAND = ""


def _load_pixbuf_from_bytes(image_bytes: bytes, size: int):
    from fabric.utils import GdkPixbuf

    loader = GdkPixbuf.PixbufLoader()
    loader.write(image_bytes)
    loader.close()
    pixbuf = loader.get_pixbuf()
    if pixbuf is None:
        return None
    return pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)


class GitHubTrayWidget(ButtonWidget, PopoverMixin):
    """Bar button: GitHub icon, unread badge, timers and data owner."""

    def __init__(self, **kwargs):
        super().__init__(name="github_tray", **kwargs)
        config = self.config

        self._hostname = str(config.get("hostname", "")).strip()
        self._client = GitHubClient(hostname=self._hostname)
        self._busy = False
        self._generation = 0

        # dataset state (owned here, rendered by the popover content)
        self.user: dict = {}
        self.repos: list = []
        self.notifications: list = []
        self.followers: list = []
        self.web_base: str = self._client.web_base
        self.error_message: str = ""
        self.loading: bool = False
        self.loaded_once: bool = False
        self._notify_primed = False
        self._last_repos_at = 0.0
        self._last_notify_at = 0.0
        self.avatar_pixbuf = None
        self.pending_notification_id: str | None = None
        self._popover_built = False

        # detail view state (issues / pulls / workflows for one repo)
        self.detail = {"kind": None, "repo": None, "items": [], "pending": False}

        self._build_button()

        self._refresh_timer = None
        self._repo_timer = None
        self._first_timer = None
        self._start_timers()

    @property
    def cache_ttl(self) -> int:
        """Seconds profile + repo data stays cached; ``0`` disables caching."""
        return max(0, int(self.config.get("cache_ttl", DEFAULT_CACHE_TTL)))

    # -- bar button --
    def _build_button(self):
        content = Box(
            orientation="h",
            spacing=0,
            style_classes="github-tray-bar-content",
        )
        content.add(
            nerd_font_icon(
                icon=self.config.get("icon", _GLYPH_BRAND),
                props={"style_classes": ["panel-font-icon"]},
            )
        )
        if self.config.get("label", False):
            content.add(
                Label(
                    label=self.config.get("label_text", "GitHub"),
                    style_classes="panel-text",
                )
            )

        # Sibling of the icon, not an Overlay: negative margins pull it over the glyph.
        self.badge_label = Label(
            label="",
            name="github-tray-badge",
            style_classes="github-tray-badge",
            v_align="start",
            visible=False,
        )
        self.badge_label.set_xalign(0.5)
        self.badge_label.set_yalign(0.5)
        content.add(self.badge_label)
        self.container_box.add(content)

        tooltip_text = str(
            self.config.get("tooltip_text", _("widget.github_tray.label"))
        )
        self.set_tooltip_if_enabled(tooltip_text, default=True)

        self.connect("button-press-event", self._on_press)
        # connect_clicked is off so on_click refreshes stale data before toggling.
        self.setup_popover(
            lambda: GitHubTrayPopoverContent(widget=self),
            connect_clicked=False,
        )
        self.connect("clicked", self.on_click)

    def _on_press(self, *_args):
        press_event = _args[1] if len(_args) > 1 else None
        button = getattr(press_event, "button", None)
        if button == 2:  # middle-click forces a full refresh (bypasses cache)
            self.refresh_repos(manual=True)
            return True
        return False

    def on_click(self, *_):
        self.toggle_popover()
        if (monotonic() - self._last_notify_at) > self.notify_interval:
            self.refresh(manual=True)

    # -- timers / lifecycle --
    @property
    def notify_interval(self) -> int:
        interval = int(self.config.get("notification_interval", 60))
        return max(MIN_NOTIFY_INTERVAL, interval)

    def _once(self, delay_ms: int, callback):
        timer_id = GLib.timeout_add(delay_ms, callback)
        self._register_repeater(timer_id)
        return timer_id

    def _start_timers(self):
        def _on_first(_=None):
            self._unregister_repeater(self._first_timer)
            self._first_timer = None
            self.refresh(manual=False)
            return False

        self._first_timer = self._once(1500, _on_first)

        def _notify_tick(_=None):
            self.refresh(manual=False)
            return True

        self._refresh_timer = GLib.timeout_add_seconds(
            self.notify_interval, _notify_tick
        )
        self._register_repeater(self._refresh_timer)

        def _repo_tick(_=None):
            self.refresh_repos(manual=False)
            return True

        self._repo_timer = GLib.timeout_add_seconds(REPOS_REFRESH_SECONDS, _repo_tick)
        self._register_repeater(self._repo_timer)

    # -- refresh orchestration --
    def _menu_due(self) -> bool:
        """True when profile + repo data needs a refresh."""
        if not self.loaded_once:
            return True
        ttl = self.cache_ttl
        if ttl <= 0:
            return (monotonic() - self._last_repos_at) >= REPOS_REFRESH_SECONDS
        return (monotonic() - self._last_repos_at) >= ttl

    def refresh(self, manual: bool = False) -> None:
        """Refresh notifications (and repos when stale) in the background."""
        if self._busy:
            return
        if self._menu_due():
            self.refresh_repos(manual=manual)
            return
        self.refresh_notifications(manual=manual)

    def refresh_notifications(self, manual: bool = False) -> None:
        if self._busy or not self.config.get("show_notifications", True):
            return
        self._busy = True
        generation = self._generation + 1
        self._generation = generation
        self.loading = True
        self._push_state()
        self._load_notifications_async(generation)

    def refresh_repos(self, manual: bool = False) -> None:
        if self._busy:
            return
        # Serve the fresh disk cache; a manual refresh always bypasses it.
        if not manual:
            cached = tray_state.read_menu_cache(MENU_CACHE_FILE, self.cache_ttl)
            if cached is not None:
                payload, age = cached
                self._apply_cached_menu(payload, age)
                return
        self._busy = True
        generation = self._generation + 1
        self._generation = generation
        self.loading = True
        self._push_state()
        self._load_menu_async(generation)

    @helpers.run_in_thread
    def _load_notifications_async(self, generation: int):
        flags = self._reason_flags()
        try:
            notifications = self._client.fetch_notifications()
            notifications = self._client.enrich_notification_states(notifications)
            notifications = [n for n in notifications if self._reason_allowed(n, flags)]
            idle_add(self._apply_notifications, generation, notifications, None)
        except Exception as error:
            idle_add(self._apply_notifications, generation, None, error)

    def _visible_repos(self, repos: list, username: str) -> list:
        """Repos to display; ``own_repos_only`` hides org/collaborator repos."""
        return tray_state.filter_own_repos(
            repos, username, enabled=self.config.get("own_repos_only", False)
        )

    @helpers.run_in_thread
    def _load_menu_async(self, generation: int):
        try:
            payload = self._client.fetch_menu(
                username_fallback=str(self.config.get("username", ""))
            )
            username = str((payload.get("user") or {}).get("login") or "")
            repos = self._visible_repos(payload.get("repos", []) or [], username)
            workflows = self._fetch_mapped_workflows(repos)
            idle_add(self._apply_menu, generation, payload, workflows, None)
        except Exception as error:
            idle_add(self._apply_menu, generation, None, None, error)

    def _fetch_mapped_workflows(self, repos: list[dict]) -> dict:
        mappings = tray_state.parse_local_projects(self._mappings_text())
        if not mappings:
            return {}
        limit = int(self.config.get("workflow_runs_max", 10))
        result = {}
        for repo in repos:
            full_name = repo.get("full_name")
            if full_name and full_name in mappings:
                with suppress(GitHubClientError, Exception):
                    result[full_name] = self._client.fetch_workflow_runs(
                        full_name, limit=limit
                    )
        return result

    def _mappings_text(self) -> str:
        projects = self.config.get("local_projects", {}) or {}
        if isinstance(projects, dict):
            return json.dumps(projects)
        return str(projects)

    def _reason_flags(self) -> dict:
        reasons = self.config.get("notify_reasons", {}) or {}
        flags = {
            "review": reasons.get("review_requests", True),
            "mentions": reasons.get("mentions", True),
            "assignments": reasons.get("assignments", True),
            "pr_comments": reasons.get("pr_comments", True),
            "issue_comments": reasons.get("issue_comments", True),
        }
        return {key: bool(value) for key, value in flags.items()}

    @staticmethod
    def _reason_allowed(notification: dict, flags: dict) -> bool:
        reason = notification.get("reason")
        kind = notification.get("subject", {}).get("type")
        if reason == "review_requested" and not flags.get("review", True):
            return False
        if reason in ("mention", "team_mention") and not flags.get("mentions", True):
            return False
        if reason == "assign" and not flags.get("assignments", True):
            return False
        if kind in (
            "PullRequest",
            "PullRequestReview",
            "PullRequestReviewComment",
        ) and not flags.get("pr_comments", True):
            return False
        return not (
            kind in ("Issue", "IssueComment") and not flags.get("issue_comments", True)
        )

    # -- apply (main thread) --
    def _apply_notifications(self, generation, notifications, error):
        if generation != self._generation:
            self._busy = False
            return False
        self.loading = False
        self._busy = False
        if error is not None:
            self.error_message = self._friendly_error(error)
            self._push_state()
            return False

        self.error_message = ""
        previous_ids = {str(n.get("id")) for n in self.notifications}
        self.notifications = notifications
        self._last_notify_at = monotonic()
        self.loaded_once = True

        self._maybe_notify_new(previous_ids)
        self._update_badge()
        self._push_state()
        return False

    def _apply_menu(self, generation, payload, workflows, error):
        if generation != self._generation:
            self._busy = False
            return False
        self.loading = False
        self._busy = False
        if error is not None:
            self.error_message = self._friendly_error(error)
            self._push_state()
            return False

        self.error_message = ""
        previous_state = tray_state.load_state_file(STATE_FILE)
        self.user = payload.get("user", {}) or {}
        self.repos = self._visible_repos(
            payload.get("repos", []) or [], str(self.user.get("login") or "")
        )
        self.followers = payload.get("followers", []) or []
        self.web_base = payload.get("web") or self._client.web_base
        self.loaded_once = True
        self._last_repos_at = monotonic()

        # Empty config means alerts off; diff_alerts reads it as "all on".
        alerts_cfg = self._alerts_config()
        current = {
            "repos": self.repos,
            "followers": self.followers,
            "notifications": self.notifications,
            "workflows": workflows or {},
        }
        if previous_state and alerts_cfg:
            for title, body in tray_state.diff_alerts(
                previous_state, current, alerts_cfg
            ):
                send_notification(title, body, app_name="GitHub Tray")

        merged = dict(previous_state)
        merged.update(
            {
                "repos": current["repos"],
                "followers": current["followers"],
                "workflows": current["workflows"],
                "notifications": current["notifications"],
            }
        )
        tray_state.save_state_file(STATE_FILE, merged)
        # Disk cache keeps restarts inside the TTL window without a second API hit.
        tray_state.save_menu_cache(MENU_CACHE_FILE, payload)

        self._load_avatar_async()
        self._update_badge()
        self._push_state()
        self._prime_notifications()
        return False

    def _apply_cached_menu(self, payload: dict, age: float) -> None:
        """Serve profile + repo data from the disk cache (no API call)."""
        self.loading = False
        self._busy = False
        self.error_message = ""
        user = payload.get("user", {}) or {}
        repos = self._visible_repos(
            payload.get("repos", []) or [], str(user.get("login") or "")
        )
        same_snapshot = (self.user or {}).get("login") == user.get("login") and len(
            self.repos
        ) == len(repos)
        self.user = user
        self.repos = repos
        self.followers = payload.get("followers", []) or []
        self.web_base = payload.get("web") or self._client.web_base
        self.loaded_once = True
        # Anchor freshness to the cache age so the API is only re-hit after expiry.
        self._last_repos_at = monotonic() - age
        if self.avatar_pixbuf is None:
            self._load_avatar_async()
        if same_snapshot:
            return
        self._update_badge()
        self._push_state()
        self._prime_notifications()

    def _prime_notifications(self) -> None:
        """Load the inbox right after the first menu load instead of waiting
        for the next interval tick."""
        if self.config.get("show_notifications", True) and not self._notify_primed:
            self._notify_primed = True
            self.refresh_notifications()

    def _maybe_notify_new(self, previous_ids: set[str]) -> None:
        if not self.config.get("alerts", {}).get("enabled", True):
            return
        if not self.config.get("alerts", {}).get("new_notifications", True):
            return
        if not previous_ids:
            return
        fresh = [n for n in self.notifications if str(n.get("id")) not in previous_ids]
        if not fresh:
            return
        count = len(fresh)
        send_notification(
            "GitHub Notifications",
            f"{count} new notification" + ("" if count == 1 else "s"),
            app_name="GitHub Tray",
        )

    def _alerts_config(self) -> dict:
        """Diff flags; ``{}`` means "do not alert", missing flags default True."""
        alerts = self.config.get("alerts", {}) or {}
        if not alerts.get("enabled", True):
            return {}
        return {
            "stars": alerts.get("new_stars", True),
            "forks": alerts.get("new_forks", True),
            "issues": alerts.get("new_issues", True),
            "followers": alerts.get("new_followers", True),
            "notifications": False,  # handled separately per interval
            "workflow_started": alerts.get("workflow_started", True),
            "workflow_success": alerts.get("workflow_success", True),
            "workflow_failure": alerts.get("workflow_failure", True),
            "workflow_cancelled": alerts.get("workflow_cancelled", True),
        }

    def _friendly_error(self, error: Exception) -> str:
        if isinstance(error, GitHubClientError):
            if error.needs_auth:
                return "GitHub is not reachable — run `gh auth login` first."
            return str(error)
        return str(error) or "Something went wrong talking to the GitHub CLI"

    # -- avatar --
    def _load_avatar_async(self):
        avatar_url = str(self.user.get("avatar_url") or "")
        if not avatar_url:
            return

        @helpers.run_in_thread
        def _fetch(url: str, size: int):
            pixbuf = None
            with suppress(Exception):
                response = get_http_client().get(url, timeout=8)
                pixbuf = _load_pixbuf_from_bytes(response.content, size)
            idle_add(self._apply_avatar, pixbuf)

        size = int(self.config.get("avatar_size", 44))
        _fetch(avatar_url, size)

    def _apply_avatar(self, pixbuf):
        if pixbuf is not None:
            self.avatar_pixbuf = pixbuf
            self._push_state()

    # -- badge / state push --
    @property
    def unread_count(self) -> int:
        return len(self.notifications)

    def _update_badge(self):
        count = self.unread_count
        if count > 0:
            self.badge_label.set_label("99+" if count > 99 else str(count))
            self.badge_label.set_visible(True)
            self.set_tooltip_text(
                f"GitHub Tray — {count} unread"
            ) if self.tooltips_enabled else None
        else:
            self.badge_label.set_visible(False)
            self.badge_label.set_label("")

    def _popover_content(self):
        popup = self.popup
        return None if popup is None else popup.content

    def show_popover(self, *_):
        """Open the popover, then rebuild its content for the now-visible window."""
        super().show_popover(*_)
        content = self._popover_content()
        if content is None:
            return
        if self._popover_built:
            # Pushes made while hidden were skipped, and relative ages must be fresh.
            if hasattr(content, "invalidate_render_cache"):
                content.invalidate_render_cache()
            if hasattr(content, "on_widget_data_changed"):
                content.on_widget_data_changed()
        self._popover_built = True

    def _push_state(self):
        """Render the popover, or let the next open render it instead."""
        popup = self.popup
        if popup is None or popup.content is None:
            return
        if not popup.get_visible():
            # A hidden popover paints nothing; rendering would churn ~300 GObjects.
            return
        content = popup.content
        if hasattr(content, "on_widget_data_changed"):
            content.on_widget_data_changed()

    # -- detail + actions (called by the popover content) --
    def open_url(self, url: str):
        if url:
            exec_shell_async_quiet(["xdg-open", str(url)])

    def open_web(self):
        self.open_url(self.web_base)

    def repo_local_path(self, repo: dict) -> str:
        return tray_state.local_path(
            self._mappings_text(),
            str(repo.get("full_name") or ""),
            GLib.get_home_dir(),
        )

    def editor_command(self) -> str:
        return str(self.config.get("local_editor", "code") or "code")

    def open_repo(self, repo: dict):
        path = self.repo_local_path(repo)
        if path:
            exec_shell_async_quiet([self.editor_command(), path])
        else:
            self.open_url(repo.get("html_url"))
        self.hide_popover()

    def load_details(self, repo: dict, kind: str):
        if self.detail.get("pending"):
            return
        self.detail = {"kind": kind, "repo": repo, "items": [], "pending": True}
        self._push_state()
        generation = self._generation

        @helpers.run_in_thread
        def _load():
            full_name = str(repo.get("full_name") or "")
            try:
                if kind == "workflows":
                    items = self._client.fetch_workflow_runs(
                        full_name, limit=int(self.config.get("workflow_runs_max", 10))
                    )
                else:
                    payload = self._client.fetch_repo_items(full_name)
                    if kind == "issues":
                        items = payload.get("issues", [])
                    else:
                        items = payload.get("pulls", [])
                    items = items or []
                idle_add(self._apply_detail, generation, kind, repo, items, None)
            except Exception as error:
                idle_add(self._apply_detail, generation, kind, repo, None, error)

        _load()

    def _apply_detail(self, generation, kind, repo, items, error):
        self.detail = {
            "kind": kind,
            "repo": repo,
            "items": items or [],
            "pending": False,
            "error": self._friendly_error(error) if error else "",
        }
        self._push_state()

    def mark_read(self, item: dict, open_after: bool = False):
        if self.pending_notification_id is not None:
            return
        self.pending_notification_id = str(item.get("id"))
        self._push_state()
        thread_id = str(item.get("id"))

        @helpers.run_in_thread
        def _mark():
            try:
                self._client.mark_read(thread_id)
                error = None
            except Exception as exc:
                error = exc
            idle_add(self._apply_mark_read, thread_id, open_after, error)

        _mark()

    def _apply_mark_read(self, thread_id: str, open_after: bool, error):
        self.pending_notification_id = None
        if error is not None:
            self._toast(f"Failed to mark as read: {error}")
            self._push_state()
            return
        item = next(
            (n for n in self.notifications if str(n.get("id")) == thread_id), None
        )
        self.notifications = [
            n for n in self.notifications if str(n.get("id")) != thread_id
        ]
        self._update_badge()
        if open_after and item is not None:
            self.open_url(tray_state.web_notification_url(item, self.web_base))
            self.hide_popover()
        else:
            self._toast("Marked as read")
        self._push_state()

    def rerun(self, run: dict):
        full_name = str(run.get("repository_full_name") or "")
        run_id = str(run.get("id") or "")

        @helpers.run_in_thread
        def _rerun():
            try:
                self._client.rerun_failed_jobs(full_name, run_id)
                error = None
            except Exception as exc:
                error = exc
            idle_add(self._apply_rerun, error)

        _rerun()

    def _apply_rerun(self, error):
        if error is not None:
            self._toast(f"Re-run failed: {error}")
            return
        self._toast("Re-run requested")
        repo = self.detail.get("repo")
        if repo is not None and self.detail.get("kind") == "workflows":
            self.load_details(repo, "workflows")

    def _toast(self, message: str):
        content = self._popover_content()
        if content is not None and hasattr(content, "show_toast"):
            content.show_toast(message)


def exec_shell_async_quiet(command: list[str]) -> None:
    from fabric.utils import exec_shell_command_async

    with suppress(Exception):
        exec_shell_command_async(" ".join(shlex.quote(part) for part in command))


class GitHubTrayPopoverContent(Box):
    """Popover content: hero, tabs, lists, detail views, toasts."""

    def __init__(self, widget: GitHubTrayWidget, **kwargs):
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

    def _build_status(self) -> Box | None:
        widget = self.tray_widget
        if widget.error_message:
            retry = ActionIconButton(
                icon=tray_state.glyph("refresh"),
                tooltip="Retry",
                on_clicked=lambda *_: widget.refresh(manual=True),
            )
            # Chrome box, not a Button: the buttons below must stay clickable siblings.
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
                            retry,
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
            # gh is not configured yet
            return EmptyState(
                icon=tray_state.glyph("github"),
                title="GitHub Tray",
                subtitle=(
                    "Login with `gh auth login` to show your\n"
                    "notifications, repositories and Actions here."
                ),
            )
        return None

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
                            _GLYPH_BRAND,
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
                ActionIconButton(
                    icon=tray_state.glyph("refresh"),
                    tooltip="Refresh",
                    on_clicked=lambda *_: widget.refresh(manual=True),
                ),
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

    def _build_tabs(self) -> Box:
        widget = self.tray_widget
        tabs = hbox(
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
        return tabs

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

    # -- inbox --
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
                            child=hbox(
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
                                                        str(
                                                            repo.get("full_name") or ""
                                                        ),
                                                        style_classes="github-tray-notification-repo",
                                                        max_width=18,
                                                    ),
                                                    (
                                                        Pill(text=state)
                                                        if state
                                                        else Box()
                                                    ),
                                                    make_label(
                                                        tray_state.reason_label(
                                                            item.get("reason")
                                                        ),
                                                        style_classes="github-tray-notification-meta",
                                                        max_width=16,
                                                    ),
                                                    Box(h_expand=True),
                                                    make_label(
                                                        tray_state.relative_time(
                                                            item.get("updated_at")
                                                        ),
                                                        style_classes="github-tray-notification-meta",
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
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

    # -- repositories --
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

    # -- detail views (issues / pulls / workflows) --
    def _render_detail(self) -> list:
        widget = self.tray_widget
        detail = widget.detail
        repo = detail.get("repo") or {}
        kind = detail.get("kind") or "issues"

        titles = {
            "issues": "Issues",
            "pulls": "Pull Requests",
            "workflows": "Workflow Runs",
        }
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
                            titles.get(kind, "GitHub"),
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

        items = detail.get("items") or []
        if not items:
            pieces.append(
                EmptyState(
                    icon=tray_state.glyph("repo"),
                    title={
                        "issues": "No open issues",
                        "pulls": "No open pull requests",
                        "workflows": "No workflow runs",
                    }.get(kind, ""),
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

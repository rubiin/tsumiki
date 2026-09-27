"""GitHub tray bar button.

Mirrors the Omarchy "github-tray" panel (notifications, repositories, per-repo
issues/PRs/Actions, alerts, local-project mappings) inside a Tsumiki bar widget.
The bar button owns the dataset, the timers and the refresh orchestration; the
popover content lives in :mod:`widgets.github_tray.popover`.
"""

from __future__ import annotations

import json
import shlex
from contextlib import suppress
from time import monotonic

from fabric.utils import GLib, idle_add
from fabric.widgets.box import Box
from fabric.widgets.label import Label

import utils.functions as helpers
from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget
from utils.constants import APP_DATA_DIRECTORY
from utils.functions import get_http_client, send_notification
from utils.i18n import _
from utils.widget_utils import nerd_font_icon

from . import state as tray_state
from .client import GitHubClient, GitHubClientError
from .components import BRAND_GLYPH
from .popover import GitHubTrayPopoverContent

STATE_FILE = f"{APP_DATA_DIRECTORY}/github_tray_state.json"
MENU_CACHE_FILE = f"{APP_DATA_DIRECTORY}/github_tray_menu_cache.json"
STATE_INFO_FILE = f"{APP_DATA_DIRECTORY}/github_tray_state_info.json"
# In-memory throttle used when the disk cache is disabled (``cache_ttl = 0``).
REPOS_REFRESH_SECONDS = 300
DEFAULT_CACHE_TTL = 3600
MIN_NOTIFY_INTERVAL = 30


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
        # A single in-flight fetch, plus at most one coalesced follow-up.
        self._fetching = 0
        self._refresh_queued = False
        self._queued_manual = False
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
        self._avatar_url = ""
        self.pending_notification_id: str | None = None
        self._popover_built = False

        # detail view state (issues / pulls / workflows for one repo)
        self.detail = {
            "kind": None,
            "repo": None,
            "items": [],
            "pending": False,
            "error": "",
        }
        # Guards detail loads only: the fetch generation is bumped by every
        # menu/notification poll, which would discard a live drill-down.
        self._detail_generation = 0

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
                icon=self.config.get("icon", BRAND_GLYPH),
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

        self._base_tooltip = str(
            self.config.get("tooltip_text", _("widget.github_tray.label"))
        )
        self.set_tooltip_if_enabled(self._base_tooltip, default=True)

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
        if self._fetching:
            self._queue_refresh(manual)
            return
        if self._menu_due():
            self.refresh_repos(manual=manual)
            return
        self.refresh_notifications(manual=manual)

    def refresh_notifications(self, manual: bool = False) -> None:
        if self._fetching:
            self._queue_refresh(manual)
            return
        if not self.config.get("show_notifications", True):
            return
        self._start_fetch(self._load_notifications_async)

    def refresh_repos(self, manual: bool = False) -> None:
        if self._fetching:
            self._queue_refresh(manual)
            return
        # Serve the fresh disk cache; a manual refresh always bypasses it.
        if not manual:
            cached = tray_state.read_menu_cache(MENU_CACHE_FILE, self.cache_ttl)
            if cached is not None:
                payload, age = cached
                self._apply_cached_menu(payload, age)
                return
        self._start_fetch(self._load_menu_async)

    def _start_fetch(self, loader) -> None:
        """Claim the single in-flight slot and show the busy state."""
        self._generation += 1
        self._fetching = self._generation
        self.loading = True
        self._push_state()
        loader(self._generation)

    def _release_fetch(self) -> None:
        """Free the slot, then re-arm the one coalesced follow-up, if any.

        Requests that arrived mid-fetch collapsed into ``_refresh_queued``, so a
        burst of clicks costs one more round trip rather than none or N.
        """
        self._fetching = 0
        self.loading = False
        if not self._refresh_queued:
            return
        self._refresh_queued = False
        manual, self._queued_manual = self._queued_manual, False
        self.refresh(manual=manual)

    def _queue_refresh(self, manual: bool = False) -> None:
        """Remember that a refresh was asked for while one was running."""
        self._refresh_queued = True
        self._queued_manual = self._queued_manual or manual

    @helpers.run_in_thread
    def _load_notifications_async(self, generation: int):
        flags = self._reason_flags()
        try:
            notifications = self._client.fetch_notifications()
            cache = tray_state.load_state_info(STATE_INFO_FILE)
            previous = dict(cache)
            notifications = self._client.enrich_notification_states(
                notifications, cache, max_age=self._state_info_max_age()
            )
            # A cache hit on every entry must not cost an atomic write and fsync.
            if cache != previous:
                tray_state.save_state_file(STATE_INFO_FILE, cache)
            notifications = [n for n in notifications if self._reason_allowed(n, flags)]
            idle_add(self._apply_notifications, generation, notifications, None)
        except Exception as error:
            idle_add(self._apply_notifications, generation, None, error)

    def _state_info_max_age(self) -> float:
        """Cached notification states expire with the repo refresh, not the poll.

        An issue or PR only changes state when someone opens or closes it, so
        re-reading it every 60 s bought a round trip and nothing else.
        """
        if not self._last_repos_at:
            return 0.0
        return max(0.0, monotonic() - self._last_repos_at)

    def _visible_repos(self, repos: list, username: str) -> list:
        """Repos to display; ``own_repos_only`` hides org/collaborator repos."""
        return tray_state.filter_own_repos(
            repos, username, enabled=self.config.get("own_repos_only", False)
        )

    @helpers.run_in_thread
    def _load_menu_async(self, generation: int):
        try:
            payload = self._client.fetch_menu(
                username_fallback=str(self.config.get("username", "")),
                workflow_repos=self._workflow_repo_names(),
                workflow_limit=int(self.config.get("workflow_runs_max", 10)),
            )
            workflows = self._fetch_mapped_workflows(payload)
            idle_add(self._apply_menu, generation, payload, workflows, None)
        except Exception as error:
            idle_add(self._apply_menu, generation, None, None, error)

    def _workflow_alerts_enabled(self) -> bool:
        """The workflow prefetch is read only by the alert differ, so gate on it."""
        flags = self._alerts_config()
        if not flags:
            return False
        return any(
            flags.get(key, True)
            for key in (
                "workflow_started",
                "workflow_success",
                "workflow_failure",
                "workflow_cancelled",
            )
        )

    def _workflow_repo_names(self) -> list[str]:
        """Mapped repos whose runs are folded into the single menu query."""
        if not self._workflow_alerts_enabled():
            return []
        return list(tray_state.parse_local_projects(self._mappings_text()))

    def _fetch_mapped_workflows(self, payload: dict) -> dict:
        """Workflow runs for mapped repos, as arrived with the menu payload.

        They ride along in the menu query now, so an alerts-off config pays
        nothing at all — previously this was one ``gh`` process per repo.
        """
        if not self._workflow_alerts_enabled():
            return {}
        return {
            full_name: runs
            for full_name, runs in (payload.get("workflows") or {}).items()
            if runs
        }

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
            return False
        if error is not None:
            self.error_message = self._friendly_error(error)
        else:
            self.error_message = ""
            previous_ids = {str(n.get("id")) for n in self.notifications}
            self.notifications = notifications
            self._last_notify_at = monotonic()
            self.loaded_once = True
            self._maybe_notify_new(previous_ids)
            self._update_badge()
        self._push_state()
        self._release_fetch()
        return False

    def _apply_menu(self, generation, payload, workflows, error):
        if generation != self._generation:
            return False
        if error is not None:
            self.error_message = self._friendly_error(error)
            self._push_state()
            self._release_fetch()
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
        self._release_fetch()
        self._prime_notifications()
        return False

    def _apply_cached_menu(self, payload: dict, age: float) -> None:
        """Serve profile + repo data from the disk cache (no API call)."""
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
        if not self.config.get("show_notifications", True) or self._notify_primed:
            return
        self._notify_primed = True
        # A queued follow-up may already have claimed the slot.
        if not self._fetching:
            self._start_fetch(self._load_notifications_async)

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
        # Guard on the URL too: a refresh with the same avatar must not re-fetch.
        if not avatar_url or avatar_url == self._avatar_url:
            return
        self._avatar_url = avatar_url

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
        if pixbuf is None:
            # Forget the URL so a later refresh may retry this download.
            self._avatar_url = ""
            return
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
            # Routed through the per-widget flag, and restorable when the count
            # drops back to zero.
            self.set_tooltip_if_enabled(f"GitHub Tray — {count} unread", default=True)
        else:
            self.badge_label.set_visible(False)
            self.badge_label.set_label("")
            self.set_tooltip_if_enabled(self._base_tooltip, default=True)

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

    def local_mappings(self) -> dict:
        """Repo -> checkout path; parse once per render, not once per card."""
        return tray_state.parse_local_projects(self._mappings_text())

    def repo_local_path(self, repo: dict, mappings: dict | None = None) -> str:
        if mappings is None:
            mappings = self.local_mappings()
        return tray_state.mapped_path(
            mappings,
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

    def reset_detail(self) -> None:
        """Leave the drill-down and drop any load still in flight for it."""
        self._detail_generation += 1
        self.detail = {
            "kind": None,
            "repo": None,
            "items": [],
            "pending": False,
            "error": "",
        }

    def load_details(self, repo: dict, kind: str):
        if self.detail.get("pending"):
            return
        self.reset_detail()
        self.detail.update({"kind": kind, "repo": repo, "pending": True})
        self._push_state()
        generation = self._detail_generation

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
        # A drill-down is abandoned by Back or replaced by another repo; a late
        # reply must not overwrite whichever one is on screen now.
        if generation != self._detail_generation:
            return False
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

"""Unit tests for the GitHub tray helpers (pure logic, no display/gh)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest import mock

from utils import functions as functions_module
from widgets.github_tray import client as tray_client_module
from widgets.github_tray import popover as tray_popover
from widgets.github_tray import state as tray_state
from widgets.github_tray import widget as tray_module
from widgets.github_tray.client import (
    GitHubClient,
    GitHubClientError,
    _alias_for,
)
from widgets.github_tray.views import detail as tray_detail
from widgets.github_tray.views import repos as tray_repos
from widgets.github_tray.widget import GitHubTrayWidget


def _iso(seconds_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


class StateFormattingTests(unittest.TestCase):
    """Formatting and notification-semantics helpers."""

    def test_relative_time(self):
        self.assertEqual(tray_state.relative_time(None), "")
        self.assertEqual(tray_state.relative_time("not-a-date"), "")
        self.assertEqual(tray_state.relative_time(_iso(5)), "just now")
        self.assertEqual(tray_state.relative_time(_iso(120)), "2m ago")
        self.assertEqual(tray_state.relative_time(_iso(2 * 3600)), "2h ago")
        self.assertEqual(tray_state.relative_time(_iso(5 * 86400)), "5d ago")
        self.assertEqual(tray_state.relative_time(_iso(2 * 30 * 86400)), "2mo ago")
        self.assertEqual(tray_state.relative_time(_iso(400 * 86400)), "1y ago")

    def test_format_count(self):
        self.assertEqual(tray_state.format_count(0), "0")
        self.assertEqual(tray_state.format_count(999), "999")
        self.assertEqual(tray_state.format_count(1200), "1.2k")
        self.assertEqual(tray_state.format_count(3500000), "3.5M")
        self.assertEqual(tray_state.format_count(None), "0")

    def test_workflow_duration(self):
        run = {"run_started_at": _iso(125), "status": "in_progress"}
        duration = tray_state.workflow_duration(run)
        self.assertEqual(duration, "2m 5s")
        self.assertEqual(tray_state.workflow_duration({}), "")

    def test_workflow_labels(self):
        self.assertEqual(
            tray_state.workflow_status({"status": "in_progress"}), "Running"
        )
        self.assertEqual(
            tray_state.workflow_status(
                {"status": "completed", "conclusion": "failure"}
            ),
            "Failed",
        )
        self.assertEqual(
            tray_state.workflow_icon(
                {"status": "completed", "conclusion": "cancelled"}
            ),
            tray_state.glyph("cancelled"),
        )

    def test_run_tint(self):
        self.assertEqual(tray_state.run_tint({"status": "in_progress"}), "running")
        self.assertEqual(tray_state.run_tint({"status": "queued"}), "running")
        self.assertEqual(
            tray_state.run_tint({"status": "completed", "conclusion": "success"}),
            "success",
        )
        self.assertEqual(
            tray_state.run_tint({"status": "completed", "conclusion": "failure"}),
            "failure",
        )
        self.assertEqual(
            tray_state.run_tint({"status": "completed", "conclusion": "timed_out"}),
            "failure",
        )
        self.assertEqual(tray_state.run_tint({"status": "completed"}), "")
        self.assertEqual(
            tray_state.run_tint({"status": "completed", "conclusion": "cancelled"}),
            "",
        )
        self.assertEqual(
            tray_state.run_tint({"status": "completed", "conclusion": "skipped"}),
            "",
        )

    def test_notification_semantics(self):
        item = {
            "id": "1",
            "subject": {"type": "PullRequest", "title": "t"},
            "reason": "review_requested",
            "_stateInfo": {"state": "MERGED", "isDraft": False},
        }
        self.assertEqual(tray_state.notification_state(item), "Merged")
        self.assertEqual(
            tray_state.reason_label("review_requested"), "Review requested"
        )
        self.assertEqual(tray_state.notification_icon(item), tray_state.glyph("merge"))
        draft = dict(item, _stateInfo={"state": "OPEN", "isDraft": True})
        self.assertEqual(tray_state.notification_state(draft), "Draft")
        self.assertEqual(tray_state.reason_label("unknown_reason"), "unknown reason")

    def test_web_notification_url(self):
        item = {
            "subject": {
                "type": "PullRequest",
                "url": "https://api.github.com/repos/o/r/pulls/42",
            }
        }
        self.assertEqual(
            tray_state.web_notification_url(item, "https://github.com"),
            "https://github.com/o/r/pull/42",
        )

    def test_sort_repos(self):
        repos = [
            {"name": "z", "stargazers_count": 1, "updated_at": "2020-01-01T00:00:00Z"},
            {"name": "a", "stargazers_count": 9, "updated_at": "2024-01-01T00:00:00Z"},
        ]
        by_stars = tray_state.sort_repos(repos, "stars", "desc")
        self.assertEqual(by_stars[0]["name"], "a")
        by_name = tray_state.sort_repos(repos, "name", "asc")
        self.assertEqual(by_name[0]["name"], "a")
        limited = tray_state.sort_repos(repos, "updated", "desc", max_repos=1)
        self.assertEqual(len(limited), 1)

    def test_filter_own_repos(self):
        repos = [
            {"name": "mine", "owner": {"login": "octo"}},
            {"name": "org-repo", "owner": {"login": "some-org"}},
            {"name": "collab", "owner": {"login": "other-user"}},
            {"name": "no-owner"},
        ]
        own = tray_state.filter_own_repos(repos, "octo", enabled=True)
        self.assertEqual([r["name"] for r in own], ["mine", "no-owner"])
        self.assertEqual(
            len(tray_state.filter_own_repos(repos, "octo", enabled=False)), 4
        )
        self.assertEqual(tray_state.filter_own_repos([], "octo", enabled=True), [])

    def test_mappings(self):
        text = json.dumps({"owner/repo": "~/dev/repo", "o2/r2": "/abs/path"})
        self.assertEqual(
            tray_state.local_path(text, "owner/repo", "/home/u"), "/home/u/dev/repo"
        )
        self.assertEqual(tray_state.local_path(text, "o2/r2", "/home/u"), "/abs/path")
        self.assertEqual(tray_state.local_path(text, "missing", "/home/u"), "")
        self.assertEqual(
            [m["repo"] for m in tray_state.sorted_mappings(text)],
            ["o2/r2", "owner/repo"],
        )


class StateDiffTests(unittest.TestCase):
    """Alert diffing against persisted state snapshots."""

    def _repo(self, rid, name, stars=0, forks=0, issues=0):
        return {
            "id": rid,
            "name": name,
            "stargazers_count": stars,
            "forks_count": forks,
            "open_issues_count": issues,
        }

    def test_no_diff_when_unchanged(self):
        previous = {
            "repos": [self._repo(1, "r", 5, 2, 1)],
            "followers": [],
            "notifications": [],
        }
        current = {
            "repos": [self._repo(1, "r", 5, 2, 1)],
            "followers": [],
            "notifications": [],
        }
        self.assertEqual(tray_state.diff_alerts(previous, current, {}), [])

    def test_first_run_does_not_alert(self):
        current = {"repos": [self._repo(1, "r", 5)]}
        self.assertEqual(tray_state.diff_alerts({}, current, {}), [])

    def test_metric_increases_alert(self):
        previous = {
            "repos": [self._repo(1, "r", 5, 2, 1)],
            "followers": [],
            "notifications": [],
        }
        current = {
            "repos": [self._repo(1, "r", 9, 3, 4)],
            "followers": [],
            "notifications": [],
        }
        alerts = dict(tray_state.diff_alerts(previous, current, {}))
        self.assertIn("New Stars!", alerts)
        self.assertIn("New Forks Created", alerts)
        self.assertIn("New Issues Opened", alerts)

    def test_followers_and_notifications(self):
        previous = {
            "repos": [],
            "followers": [{"id": 1, "login": "old"}],
            "notifications": [{"id": "a"}],
        }
        current = {
            "repos": [],
            "followers": [{"id": 1, "login": "old"}, {"id": 2, "login": "new"}],
            "notifications": [{"id": "a"}, {"id": "b"}],
        }
        alerts = dict(tray_state.diff_alerts(previous, current, {}))
        self.assertIn("New Followers", alerts)
        self.assertIn("GitHub Notifications", alerts)

    def test_flags_disable_metric_alerts(self):
        previous = {"repos": [self._repo(1, "r", 1)]}
        current = {"repos": [self._repo(1, "r", 5)]}
        self.assertEqual(
            tray_state.diff_alerts(previous, current, {"stars": False}), []
        )

    def test_workflow_transitions(self):
        started = {
            "id": 1,
            "status": "in_progress",
            "name": "CI",
            "head_branch": "main",
        }
        failed = {
            "id": 1,
            "status": "completed",
            "conclusion": "failure",
            "name": "CI",
        }
        previous = {"workflows": {"o/r": [started]}}
        current = {"workflows": {"o/r": [failed]}}
        alerts = tray_state.diff_alerts(previous, current, {})
        self.assertEqual(alerts, [("GitHub Actions: Workflow Failed", "r • CI")])

        current_started = {"workflows": {"o/r": [started]}}
        new_alerts = tray_state.diff_alerts(
            {"workflows": {}}, current_started, {"workflow_started": True}
        )
        self.assertEqual(new_alerts[0][0], "GitHub Actions: Workflow Started")


class MenuCacheTests(unittest.TestCase):
    """Profile + repo disk-cache helpers (read/save with TTL)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = f"{self.tmpdir}/menu_cache.json"
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.payload = {
            "user": {"login": "octo", "followers": 3},
            "repos": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}],
        }

    def test_save_then_read_within_ttl(self):
        now = time.time()
        tray_state.save_menu_cache(self.cache_path, self.payload, now=now).result()
        cached = tray_state.read_menu_cache(self.cache_path, ttl=3600, now=now + 60)
        self.assertIsNotNone(cached)
        payload, age = cached
        self.assertEqual(payload, self.payload)
        self.assertAlmostEqual(age, 60, delta=1)

    def test_read_after_ttl_returns_none(self):
        now = time.time()
        tray_state.save_menu_cache(self.cache_path, self.payload, now=now).result()
        self.assertIsNone(
            tray_state.read_menu_cache(self.cache_path, ttl=3600, now=now + 3601)
        )

    def test_ttl_zero_disables_cache(self):
        now = time.time()
        tray_state.save_menu_cache(self.cache_path, self.payload, now=now).result()
        self.assertIsNone(
            tray_state.read_menu_cache(self.cache_path, ttl=0, now=now + 1)
        )

    def test_missing_or_corrupt_file_returns_none(self):
        self.assertIsNone(tray_state.read_menu_cache(self.cache_path, ttl=3600))
        with open(self.cache_path, "w", encoding="utf-8") as handle:
            handle.write("not json")
        self.assertIsNone(tray_state.read_menu_cache(self.cache_path, ttl=3600))
        # Fresh file without a valid payload is ignored too.
        tray_state.save_state_file(self.cache_path, {"cached_at": time.time()}).result()
        self.assertIsNone(tray_state.read_menu_cache(self.cache_path, ttl=3600))

    def test_state_writer_uses_shared_json_writer(self):
        with mock.patch.object(tray_state, "write_json_file") as writer:
            tray_state._write_state_file(self.cache_path, {"a": 1})

        writer.assert_called_once_with(self.cache_path, {"a": 1}, sync=True)

    def test_save_state_file_is_offloaded_to_thread_pool(self):
        """Widget state writes must not run on the caller's thread."""
        with mock.patch("widgets.github_tray.state.thread") as pooled:
            future = tray_state.save_state_file(self.cache_path, {"a": 1})

        pooled.assert_called_once()
        self.assertIs(future, pooled.return_value)
        self.assertFalse(os.path.exists(self.cache_path))

    def test_clock_skew_backwards_is_not_fresh(self):
        now = time.time()
        tray_state.save_menu_cache(self.cache_path, self.payload, now=now).result()
        # A cache stamped in the future must never be treated as fresh.
        self.assertIsNone(
            tray_state.read_menu_cache(self.cache_path, ttl=3600, now=now - 60)
        )


class _MenuApplyHarness:
    """Runs the real ``_apply_menu`` logic without building a GTK widget."""

    _apply_menu = GitHubTrayWidget._apply_menu
    _alerts_config = GitHubTrayWidget._alerts_config
    _visible_repos = GitHubTrayWidget._visible_repos
    _release_fetch = GitHubTrayWidget._release_fetch

    def __init__(self, config, notifications=()):
        self.config = config
        self._client = mock.Mock(web_base="https://github.com")
        self._generation = 1
        self._fetching = 1
        self._refresh_queued = False
        self._queued_manual = False
        self.loading = True
        self.error_message = ""
        self.loaded_once = False
        self._last_repos_at = 0.0
        self.avatar_pixbuf = None
        self.user = {}
        self.repos = []
        self.followers = []
        self.notifications = list(notifications)

    # no-op stand-ins for the UI touchpoints
    def _load_avatar_async(self):
        pass

    def _update_badge(self):
        pass

    def _push_state(self):
        pass

    def _prime_notifications(self):
        pass


class MenuApplyAlertTests(unittest.TestCase):
    """Desktop alerts fired by the menu-apply path honour the alerts config."""

    def _repo(self, rid, name, stars=0, forks=0, issues=0):
        return {
            "id": rid,
            "name": name,
            "full_name": f"octo/{name}",
            "stargazers_count": stars,
            "forks_count": forks,
            "open_issues_count": issues,
        }

    def _run(self, alerts, previous, payload, workflows=None):
        harness = _MenuApplyHarness({"alerts": alerts})
        with (
            mock.patch.object(tray_state, "load_state_file", return_value=previous),
            mock.patch.object(tray_state, "save_state_file") as save,
            mock.patch.object(tray_state, "save_menu_cache"),
            mock.patch.object(tray_module, "send_notification") as sent,
        ):
            harness._apply_menu(1, payload, workflows, None)
        titles = {call.args[0] for call in sent.call_args_list}
        return titles, save

    def test_alerts_disabled_fires_nothing(self):
        """alerts.enabled = false must not notify, even with every sub-flag on."""
        previous = {
            "repos": [self._repo(1, "r", 1, 0, 0)],
            "followers": [{"id": 1, "login": "old"}],
            "notifications": [],
            "workflows": {"octo/r": [{"id": 1, "status": "in_progress", "name": "CI"}]},
        }
        payload = {
            "user": {"login": "octo"},
            "repos": [self._repo(1, "r", 9, 4, 3)],
            "followers": [{"id": 1, "login": "old"}, {"id": 2, "login": "new"}],
        }
        workflows = {
            "octo/r": [
                {"id": 1, "status": "completed", "conclusion": "failure", "name": "CI"}
            ]
        }
        alerts = {
            "enabled": False,
            "new_stars": True,
            "new_forks": True,
            "new_issues": True,
            "new_followers": True,
            "workflow_failure": True,
        }

        titles, _ = self._run(alerts, previous, payload, workflows)

        self.assertEqual(titles, set())

    def test_alerts_enabled_fires_only_enabled_categories(self):
        previous = {
            "repos": [self._repo(1, "r", 1, 1, 1)],
            "followers": [{"id": 1, "login": "old"}],
            "notifications": [],
            "workflows": {"octo/r": [{"id": 1, "status": "in_progress", "name": "CI"}]},
        }
        payload = {
            "user": {"login": "octo"},
            "repos": [self._repo(1, "r", 9, 4, 3)],
            "followers": [{"id": 1, "login": "old"}, {"id": 2, "login": "new"}],
        }
        workflows = {
            "octo/r": [
                {"id": 1, "status": "completed", "conclusion": "failure", "name": "CI"}
            ]
        }
        alerts = {
            "enabled": True,
            "new_stars": True,
            "new_forks": False,
            "new_issues": False,
            "new_followers": False,
            "workflow_failure": True,
        }

        titles, _ = self._run(alerts, previous, payload, workflows)

        self.assertEqual(titles, {"New Stars!", "GitHub Actions: Workflow Failed"})

    def test_alerts_disabled_still_saves_state(self):
        """The opt-out suppresses notifications, not the snapshot diff needs."""
        previous = {"repos": [self._repo(1, "r", 1)], "followers": []}
        payload = {
            "user": {"login": "octo"},
            "repos": [self._repo(1, "r", 9)],
            "followers": [{"id": 2, "login": "new"}],
        }
        disabled = {"enabled": False, "new_stars": True, "new_followers": True}

        _, save = self._run(disabled, previous, payload, None)

        save.assert_called_once()
        path, merged = save.call_args.args
        self.assertTrue(path.endswith("github_tray_state.json"))
        self.assertEqual([repo["stargazers_count"] for repo in merged["repos"]], [9])
        # Feeding the saved snapshot back in must not re-alert.
        titles, _ = self._run(
            {"enabled": True, "new_stars": True, "new_followers": True},
            merged,
            payload,
            None,
        )
        self.assertEqual(titles, set())


class _StubPopover:
    """Minimal stand-in for ``shared.popover.Popover``."""

    def __init__(self, content, visible=False):
        self.content = content
        self._visible = visible
        self.open_count = 0

    def get_visible(self):
        return self._visible

    def open(self, *_):
        self._visible = True
        self.open_count += 1


class _StubContent:
    """Counts renders instead of building ~300 GObjects."""

    def __init__(self):
        self.renders = 0
        self.invalidations = 0

    def invalidate_render_cache(self):
        self.invalidations += 1

    def on_widget_data_changed(self):
        self.renders += 1


class _RenderHarness(GitHubTrayWidget):
    """Real render gating; the popover, badge and style calls are stubbed."""

    def __init__(self, content, visible=False, config=None):
        self._popup = _StubPopover(content, visible)
        self._popover_built = True
        self.badge_label = mock.Mock()
        self.tooltips_enabled = False
        self.config = {} if config is None else config
        self._base_tooltip = "GitHub Tray"
        self.notifications = []


class PopoverRenderGatingTests(unittest.TestCase):
    """Hidden popovers must not rebuild their widget tree on every poll."""

    def setUp(self):
        self.content = _StubContent()
        self.widget = _RenderHarness(self.content)
        patcher = mock.patch.object(GitHubTrayWidget, "add_style_class")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_push_state_while_hidden_does_not_render(self):
        """A 60s poll with a closed popover must not touch the widget tree."""
        self.widget._push_state()

        self.assertEqual(self.content.renders, 0)

    def test_push_state_while_visible_renders(self):
        """Visible popovers keep re-rendering on data changes."""
        self.widget._popup._visible = True

        self.widget._push_state()

        self.assertEqual(self.content.renders, 1)

    def test_opening_after_hidden_push_renders_once(self):
        """Data that arrived while hidden is drawn by the next open."""
        self.widget._push_state()
        self.assertEqual(self.content.renders, 0)

        self.widget.show_popover()

        self.assertEqual(self.widget._popup.open_count, 1)
        self.assertEqual(self.content.renders, 1)
        self.assertEqual(self.content.invalidations, 1)

    def test_reopening_renders_again_for_fresh_ages(self):
        self.widget.show_popover()
        self.widget._popup._visible = False

        self.widget.show_popover()

        self.assertEqual(self.content.renders, 2)
        self.assertEqual(self.content.invalidations, 2)

    def test_first_open_does_not_double_render(self):
        """Content builds itself in its constructor, so open must not repeat it."""
        self.widget._popover_built = False
        self.content.renders = 1

        self.widget.show_popover()

        self.assertEqual(self.content.renders, 1)
        self.assertEqual(self.content.invalidations, 0)

    def test_badge_updates_while_popover_hidden(self):
        """The bar button is always visible, so it keeps updating off-screen."""
        self.widget.notifications = [{"id": "1"}, {"id": "2"}, {"id": "3"}]

        self.widget._update_badge()

        self.assertEqual(self.widget.unread_count, 3)
        self.widget.badge_label.set_label.assert_called_once_with("3")
        self.widget.badge_label.set_visible.assert_called_once_with(True)
        self.assertEqual(self.content.renders, 0)

    def test_badge_clears_when_no_notifications(self):
        self.widget.badge_label.set_label.reset_mock()
        self.widget.badge_label.set_visible.reset_mock()

        self.widget._update_badge()

        self.assertEqual(self.widget.unread_count, 0)
        self.widget.badge_label.set_label.assert_called_once_with("")
        self.widget.badge_label.set_visible.assert_called_once_with(False)


class BadgeTooltipTests(unittest.TestCase):
    """The badge tooltip is a temporary override, not a replacement."""

    def _widget(self, config=None):
        widget = _RenderHarness(_StubContent(), config=config)
        widget.tooltips_enabled = True
        self.tooltips: list[str] = []
        patcher = mock.patch.object(
            GitHubTrayWidget,
            "set_tooltip_text",
            side_effect=self.tooltips.append,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return widget

    def test_unread_items_replace_the_tooltip(self):
        widget = self._widget()
        widget.notifications = [{"id": str(index)} for index in range(7)]

        widget._update_badge()

        self.assertEqual(["GitHub Tray — 7 unread"], self.tooltips)

    def test_the_configured_tooltip_comes_back_at_zero(self):
        widget = self._widget()
        widget.notifications = [{"id": "1"}]
        widget._update_badge()

        widget.notifications = []
        widget._update_badge()

        self.assertEqual(["GitHub Tray — 1 unread", "GitHub Tray"], self.tooltips)

    def test_the_per_widget_flag_is_honoured(self):
        """``tooltip = false`` must not be overridden by the badge."""
        widget = self._widget(config={"tooltip": False})
        widget.notifications = [{"id": "1"}]

        widget._update_badge()

        self.assertEqual([], self.tooltips)
        widget.badge_label.set_visible.assert_called_once_with(True)

    def test_a_disabled_tooltip_leaves_the_previous_text_alone(self):
        widget = self._widget(config={"tooltip": False})
        widget.notifications = [{"id": "1"}]
        widget._update_badge()

        widget.notifications = []
        widget._update_badge()

        self.assertEqual([], self.tooltips)


class _TrayStateStub:
    """Data snapshot the render key is derived from."""

    def __init__(self):
        self.notifications: list = []
        self.repos: list = []
        self.user: dict = {}
        self.detail = {"kind": None}
        self.loading = False
        self.loaded_once = True
        self.error_message = ""
        self.avatar_pixbuf = None
        self.web_base = "https://github.com"
        self.pending_notification_id = None


class _RenderKeyHarness:
    """Borrows ``_render_key`` so the memo can be checked without GTK."""

    _render_key = tray_popover.GitHubTrayPopoverContent._render_key

    def __init__(self):
        self._view = "main"
        self._tab = "inbox"
        self._notify_page = 0
        self.tray_widget = _TrayStateStub()


class RenderKeyTests(unittest.TestCase):
    """The render memo only skips rebuilds when nothing visible changed."""

    def setUp(self):
        self.harness = _RenderKeyHarness()
        self._load_snapshot()

    def _load_snapshot(self):
        """Reset the data to a known baseline."""
        state = self.harness.tray_widget
        state.notifications = [
            {"id": "1", "subject": {"title": "fix bug"}, "reason": "mention"}
        ]
        state.repos = [{"full_name": "octo/r", "stargazers_count": 3}]

    def test_identical_state_yields_identical_key(self):
        first = self.harness._render_key()
        self._load_snapshot()

        self.assertEqual(first, self.harness._render_key())

    def test_changed_notification_forces_a_new_key(self):
        first = self.harness._render_key()
        self.harness.tray_widget.notifications[0]["_stateInfo"] = {"state": "MERGED"}

        self.assertNotEqual(first, self.harness._render_key())

    def test_changed_repo_metric_forces_a_new_key(self):
        first = self.harness._render_key()
        self.harness.tray_widget.repos[0]["stargazers_count"] = 4

        self.assertNotEqual(first, self.harness._render_key())

    def test_tab_page_and_pending_state_force_a_new_key(self):
        first = self.harness._render_key()
        self.harness._tab = "repos"
        after_tab = self.harness._render_key()
        self.harness._tab = "inbox"
        self.harness._notify_page = 1
        after_page = self.harness._render_key()
        self.harness._notify_page = 0
        self.harness.tray_widget.pending_notification_id = "1"
        after_pending = self.harness._render_key()

        self.assertNotEqual(first, after_tab)
        self.assertNotEqual(first, after_page)
        self.assertNotEqual(first, after_pending)

    def test_detail_view_is_never_memoised(self):
        self.harness._view = "issues"

        self.assertIsNone(self.harness._render_key())


class _WorkflowHarness:
    """Real workflow-planning logic; no GTK, no client, no API."""

    _fetch_mapped_workflows = GitHubTrayWidget._fetch_mapped_workflows
    _workflow_alerts_enabled = GitHubTrayWidget._workflow_alerts_enabled
    _workflow_repo_names = GitHubTrayWidget._workflow_repo_names
    _alerts_config = GitHubTrayWidget._alerts_config
    _mappings_text = GitHubTrayWidget._mappings_text

    def __init__(self, config):
        self.config = config
        self._client = mock.Mock()


class WorkflowPrefetchTests(unittest.TestCase):
    """The mapped-repo run prefetch must cost nothing when alerts are off."""

    def _config(self, alerts):
        return {
            "alerts": alerts,
            "local_projects": {"octo/r": "/tmp/r", "octo/other": "/tmp/other"},
        }

    def test_no_process_is_spawned_when_alerts_are_disabled(self):
        harness = _WorkflowHarness(self._config({"enabled": False}))
        payload = {"workflows": {"octo/r": [{"id": 1, "status": "in_progress"}]}}

        with _patch_spawn({}) as run:
            result = harness._fetch_mapped_workflows(payload)

        self.assertEqual(result, {})
        run.assert_not_called()

    def test_disabled_alerts_never_ask_for_runs(self):
        """The query is not even widened, so the menu payload stays one call."""
        harness = _WorkflowHarness(self._config({"enabled": False}))

        self.assertEqual(harness._workflow_repo_names(), [])

    def test_all_workflow_flags_off_also_skips_the_prefetch(self):
        config = self._config(
            {
                "enabled": True,
                "new_stars": True,
                "workflow_started": False,
                "workflow_success": False,
                "workflow_failure": False,
                "workflow_cancelled": False,
            }
        )
        harness = _WorkflowHarness(config)

        with _patch_spawn({}) as run:
            result = harness._fetch_mapped_workflows(
                {"workflows": {"octo/r": [{"id": 1}]}}
            )

        self.assertEqual(result, {})
        run.assert_not_called()

    def test_enabled_alerts_keep_the_folded_runs(self):
        harness = _WorkflowHarness(self._config({"enabled": True}))
        runs = [{"id": 1, "status": "in_progress", "conclusion": None}]

        with _patch_spawn({}) as run:
            result = harness._fetch_mapped_workflows({"workflows": {"octo/r": runs}})

        self.assertEqual(result, {"octo/r": runs})
        run.assert_not_called()
        self.assertEqual(harness._workflow_repo_names(), ["octo/r", "octo/other"])

    def test_repos_without_runs_are_dropped(self):
        harness = _WorkflowHarness(self._config({"enabled": True}))

        result = harness._fetch_mapped_workflows(
            {"workflows": {"octo/r": [{"id": 1}], "octo/other": []}}
        )

        self.assertEqual(result, {"octo/r": [{"id": 1}]})


class MenuQueryFoldingTests(unittest.TestCase):
    """Workflow rides along in the menu query instead of a process per repo."""

    def _menu_data(self, runs_by_alias):
        return {
            "data": {
                "viewer": {
                    "login": "octo",
                    "repositories": {"totalCount": 0, "nodes": []},
                    "followersList": {"nodes": []},
                },
                **runs_by_alias,
            }
        }

    def test_mapped_repos_cost_no_extra_process(self):
        payload = self._menu_data(
            {
                "wf0": {
                    "workflowRuns": {
                        "nodes": [
                            {
                                "databaseId": 5,
                                "name": "CI",
                                "displayTitle": "fix",
                                "status": "completed",
                                "conclusion": "success",
                                "headBranch": "main",
                                "url": "https://github.com/octo/r/actions/runs/5",
                                "createdAt": "2024-01-01T00:00:00Z",
                                "updatedAt": "2024-01-01T00:05:00Z",
                            }
                        ]
                    }
                }
            }
        )
        with _patch_spawn(payload) as run:
            menu = GitHubClient().fetch_menu(
                workflow_repos=["octo/r", "octo/other"], workflow_limit=5
            )

        self.assertEqual(run.call_count, 1)
        query = next(
            part for part in run.call_args[0][0] if str(part).startswith("query=")
        )
        self.assertIn('name: "r"', query)
        self.assertIn("workflowRuns(first: 5", query)
        # Both repos are asked for in that one call; only the one with runs
        # reaches the caller, so an empty repo costs nothing downstream.
        self.assertIn('name: "other"', query)
        self.assertEqual(sorted(menu["workflows"]), ["octo/r"])
        run_data = menu["workflows"]["octo/r"][0]
        self.assertEqual(run_data["id"], 5)
        self.assertEqual(run_data["head_branch"], "main")
        self.assertEqual(run_data["repository_full_name"], "octo/r")

    def test_a_repo_the_token_cannot_see_is_skipped(self):
        payload = self._menu_data({"wf0": None, "wf1": None})
        with _patch_spawn(payload) as run:
            menu = GitHubClient().fetch_menu(workflow_repos=["octo/r", "octo/other"])

        self.assertEqual(run.call_count, 1)
        self.assertEqual(menu["workflows"], {})


class _RefreshHarness:
    """Real refresh scheduling; the client and GTK are stubbed out."""

    refresh = GitHubTrayWidget.refresh
    refresh_notifications = GitHubTrayWidget.refresh_notifications
    refresh_repos = GitHubTrayWidget.refresh_repos
    _start_fetch = GitHubTrayWidget._start_fetch
    _release_fetch = GitHubTrayWidget._release_fetch
    _queue_refresh = GitHubTrayWidget._queue_refresh

    def __init__(self, config=None, menu_due=False):
        self.config = config if config is not None else {"show_notifications": True}
        self._generation = 0
        self._fetching = 0
        self._refresh_queued = False
        self._queued_manual = False
        self.loading = False
        self._menu_due_flag = menu_due
        self.fetched = 0
        self.paused = True

    def _menu_due(self):
        return self._menu_due_flag

    cache_ttl = 3600

    def _push_state(self):
        pass

    def _apply_notifications(self, generation, notifications, error):
        self._release_fetch()

    def _load_menu_async(self, generation):
        self.fetched += 1

    def _load_notifications_async(self, generation):
        self.fetched += 1
        if not self.paused:
            self._apply_notifications(generation, None, None)


class CoalescingRefreshTests(unittest.TestCase):
    """A refresh asked for mid-fetch re-arms exactly one follow-up."""

    def setUp(self):
        self.harness = _RefreshHarness()

    def test_a_refresh_during_a_fetch_is_queued(self):
        self.harness.refresh()

        self.harness.refresh()

        self.assertEqual(self.harness.fetched, 1)
        self.assertTrue(self.harness._refresh_queued)

    def test_repeated_requests_collapse_into_one_follow_up(self):
        self.harness.refresh()
        for _ in range(5):
            self.harness.refresh()
        self.harness.paused = False

        self.harness._apply_notifications(self.harness._generation, None, None)

        self.assertEqual(self.harness.fetched, 2)
        self.assertFalse(self.harness._refresh_queued)

    def test_a_manual_request_survives_the_coalescing(self):
        """The follow-up must still bypass the cache, or the click is a no-op."""
        self.harness.refresh()
        self.harness.refresh(manual=True)
        self.harness.refresh()
        self.harness.paused = False

        self.harness._apply_notifications(self.harness._generation, None, None)

        self.assertFalse(self.harness._queued_manual)
        self.assertEqual(self.harness.fetched, 2)

    def test_no_follow_up_when_nothing_was_queued(self):
        self.harness.refresh()
        self.harness.paused = False

        self.harness._apply_notifications(self.harness._generation, None, None)

        self.assertEqual(self.harness.fetched, 1)
        self.assertFalse(self.harness._refresh_queued)

    def test_repos_refresh_queues_instead_of_vanishing(self):
        harness = _RefreshHarness(menu_due=True)
        with mock.patch.object(tray_state, "read_menu_cache", return_value=None):
            harness.refresh_repos()

            harness.refresh_repos(manual=True)

        self.assertTrue(harness._refresh_queued)
        self.assertEqual(harness.fetched, 1)


def _patch_spawn(payload=None, returncode=0, stderr="", stdout=None):
    """Intercept the process runner the ``gh`` fallback goes through."""
    if stdout is None:
        stdout = json.dumps(payload) if payload is not None else ""
    result = (returncode, stdout, stderr, None)
    return mock.patch.object(functions_module, "_spawn_and_wait", return_value=result)


class ClientTests(unittest.TestCase):
    """gh CLI command construction and error mapping."""

    _patch_run = staticmethod(_patch_spawn)

    def test_fetch_menu_command_shape(self):
        payload = {"data": {"viewer": {"login": "octo", "repositories": {"nodes": []}}}}
        with self._patch_run(payload) as run:
            client = GitHubClient()
            client.fetch_menu()
            command = run.call_args[0][0]
        self.assertEqual(command[:3], ["gh", "api", "graphql"])
        self.assertIn("-f", command)
        self.assertTrue(any("viewer" in part for part in command))
        self.assertNotIn("--hostname", command)

    def test_hostname_flag(self):
        payload = {"data": {"viewer": {}}}
        with self._patch_run(payload) as run:
            GitHubClient(hostname="ghe.example.com").fetch_menu()
            command = run.call_args[0][0]
        self.assertEqual(command[-2:], ["--hostname", "ghe.example.com"])

    def test_http_error_raises_with_auth_hint(self):
        with (
            self._patch_run(
                {}, returncode=1, stderr="gh: HTTP 401 Unauthorized (Bad credentials)"
            ),
            self.assertRaises(GitHubClientError) as ctx,
        ):
            GitHubClient().fetch_menu()
        self.assertTrue(ctx.exception.needs_auth)

    def test_plain_error_message(self):
        with (
            self._patch_run({}, returncode=1, stderr="gh: HTTP 404 Not Found"),
            self.assertRaises(GitHubClientError) as ctx,
        ):
            GitHubClient().fetch_menu()
        self.assertFalse(ctx.exception.needs_auth)

    def test_mark_read_and_rerun(self):
        with self._patch_run({}) as run:
            GitHubClient().mark_read("123")
            GitHubClient().rerun_failed_jobs("o/r", "9")
        # The token mint is not an API call; only the two mutations matter here.
        calls = [args[0] for args, _ in run.call_args_list if "api" in args[0][1:2]]
        first, second = calls
        self.assertIn("PATCH", first)
        self.assertIn("notifications/threads/123", first)
        self.assertIn("POST", second)
        self.assertIn("repos/o/r/actions/runs/9/rerun-failed-jobs", second)

    def test_enrichment_uses_aliased_query(self):
        notification = {
            "id": "9001",
            "subject": {
                "type": "Issue",
                "url": "https://api.github.com/repos/o/r/issues/7",
            },
        }
        payload = {"data": {"n9001": {"issue": {"state": "CLOSED", "isDraft": False}}}}
        with self._patch_run(payload) as run:
            GitHubClient().enrich_notification_states([notification])
            command = run.call_args[0][0]
        query = next(part for part in command if part.startswith("query="))
        self.assertIn("n9001", query)
        self.assertIn("issue(number: 7)", query)
        self.assertEqual(notification["_stateInfo"]["state"], "CLOSED")


class NotificationStateCacheTests(unittest.TestCase):
    """``_stateInfo`` is cached per repo/number and re-queried only when stale."""

    NOW = 1_700_000_000.0

    def _notification(self, nid="9001", number=7, kind="issues", updated_at=""):
        return {
            "id": nid,
            "updated_at": updated_at,
            "subject": {
                "type": "Issue" if kind == "issues" else "PullRequest",
                "url": f"https://api.github.com/repos/o/r/{kind}/{number}",
            },
        }

    def _state(self, state="OPEN", at=None, is_draft=False):
        return {
            "at": self.NOW if at is None else at,
            "state": state,
            "isDraft": is_draft,
        }

    def test_a_cached_entry_is_not_re_queried(self):
        """States change when a PR is opened or closed, not every 60 seconds."""
        notification = self._notification()
        cache = {"o/r#7": self._state()}

        with _patch_spawn({}) as run:
            GitHubClient().enrich_notification_states(
                [notification], cache, max_age=300, now=self.NOW
            )

        run.assert_not_called()
        self.assertEqual(notification["_stateInfo"]["state"], "OPEN")

    def test_a_stale_entry_is_requeried_after_the_repo_refresh(self):
        notification = self._notification()
        cache = {"o/r#7": self._state(at=self.NOW - 600)}
        payload = {"data": {"n9001": {"issue": {"state": "CLOSED"}}}}

        with _patch_spawn(payload) as run:
            GitHubClient().enrich_notification_states(
                [notification], cache, max_age=300, now=self.NOW
            )

        self.assertEqual(run.call_count, 1)
        self.assertEqual(notification["_stateInfo"]["state"], "CLOSED")
        self.assertEqual(cache["o/r#7"]["at"], self.NOW)

    def test_newer_thread_activity_requeries_the_state(self):
        """A comment since the entry was cached means the state may have moved."""
        notification = self._notification(updated_at="2023-11-14T22:15:00+00:00")
        cache = {"o/r#7": self._state(at=self.NOW - 10)}
        payload = {"data": {"n9001": {"issue": {"state": "MERGED"}}}}

        with _patch_spawn(payload) as run:
            GitHubClient().enrich_notification_states(
                [notification], cache, max_age=86400, now=self.NOW
            )

        self.assertEqual(run.call_count, 1)
        self.assertEqual(notification["_stateInfo"]["state"], "MERGED")

    def test_draft_state_round_trips_through_the_cache(self):
        notification = self._notification(kind="pulls")
        cache = {"o/r#7": self._state(is_draft=True)}

        with _patch_spawn({}) as run:
            GitHubClient().enrich_notification_states(
                [notification], cache, max_age=300, now=self.NOW
            )

        run.assert_not_called()
        self.assertEqual(
            tray_state.notification_state(notification),
            "Draft",
        )

    def test_an_alias_collision_no_longer_loses_the_batch(self):
        """Both ids sanitise to the same alias, which used to void the query."""
        first = self._notification(nid="1_a")
        second = self._notification(nid="1/a", number=8)
        payload = {
            "data": {
                "n1_a": {"issue": {"state": "OPEN"}},
                "n1_a_2": {"issue": {"state": "CLOSED"}},
            }
        }

        with _patch_spawn(payload) as run:
            GitHubClient().enrich_notification_states(
                [first, second], {}, max_age=0, now=self.NOW
            )
            query = next(
                part for part in run.call_args[0][0] if str(part).startswith("query=")
            )

        self.assertEqual(first["_stateInfo"]["state"], "OPEN")
        self.assertEqual(second["_stateInfo"]["state"], "CLOSED")
        self.assertEqual(query.count("issue(number:"), 2)

    def test_a_non_numeric_id_is_still_enriched(self):
        """Thread ids are base64-ish; a digit-only alias collided on all of them."""
        first = self._notification(nid="PR_kwDOAbcDef", number=7)
        second = self._notification(nid="PR_kwDOAbcGhi", number=8)
        taken: set = set()
        aliases = [_alias_for(first, taken), _alias_for(second, taken)]
        self.assertEqual(len(set(aliases)), 2)
        for alias in aliases:
            self.assertRegex(alias, r"^[_A-Za-z][_0-9A-Za-z]*$")

        payload = {
            "data": {
                aliases[0]: {"issue": {"state": "OPEN"}},
                aliases[1]: {"issue": {"state": "CLOSED"}},
            }
        }
        with _patch_spawn(payload) as run:
            GitHubClient().enrich_notification_states(
                [first, second], {}, max_age=0, now=self.NOW
            )
            query = next(
                part for part in run.call_args[0][0] if str(part).startswith("query=")
            )

        self.assertEqual(query.count("issue(number:"), 2)
        self.assertEqual(first["_stateInfo"]["state"], "OPEN")
        self.assertEqual(second["_stateInfo"]["state"], "CLOSED")

    def test_a_failed_query_is_logged_and_keeps_the_cache(self):
        """Returning bare notifications silently left every pill blank."""
        notification = self._notification()
        cache = {"o/r#7": self._state(at=self.NOW - 600)}

        with (
            _patch_spawn({}, returncode=1, stderr="gh: HTTP 500"),
            mock.patch.object(tray_client_module, "logger") as logger,
        ):
            GitHubClient().enrich_notification_states(
                [notification], cache, max_age=300, now=self.NOW
            )

        logger.warning.assert_called_once()
        self.assertNotIn("_stateInfo", notification)
        self.assertIn("o/r#7", cache)

    def test_the_cache_is_pruned_to_the_current_inbox(self):
        first = self._notification(nid="1", number=7)
        second = self._notification(nid="2", number=8)
        cache = {"o/r#7": self._state(), "o/gone#1": self._state()}
        payload = {
            "data": {
                "n1": {"issue": {"state": "OPEN"}},
                "n2": {"issue": {"state": "CLOSED"}},
            }
        }

        with _patch_spawn(payload):
            GitHubClient().enrich_notification_states(
                [first, second], cache, max_age=0, now=self.NOW
            )

        # A notification that left the inbox cannot keep an entry alive.
        self.assertEqual(sorted(cache), ["o/r#7", "o/r#8"])


class TransportTests(unittest.TestCase):
    """REST goes through the pooled client once ``gh`` has minted a token."""

    TOKEN = "gho_0123456789abcdef"

    def _response(self, status=200, payload=None):
        response = mock.Mock()
        response.status_code = status
        response.content = b"x"
        response.json.return_value = [] if payload is None else payload
        response.text = json.dumps({"message": "Bad credentials"})
        return response

    def _spawn_token_then_api(self, spawn_log):
        """gh auth token yields a token; anything else yields a JSON payload."""

        def _run(cmd, timeout=None, check=False):
            spawn_log.append(list(cmd))
            if "token" in cmd:
                return (0, f"{self.TOKEN}\n", "", None)
            return (0, "[]", "", None)

        return _run

    @contextmanager
    def _patched(self, spawn_log, http):
        with (
            mock.patch.object(
                functions_module,
                "_spawn_and_wait",
                side_effect=self._spawn_token_then_api(spawn_log),
            ),
            mock.patch.object(tray_client_module, "get_http_client", return_value=http),
        ):
            yield

    def test_rest_uses_the_pooled_client_with_a_bearer_token(self):
        spawn_log: list = []
        http = mock.Mock()
        http.request.return_value = self._response()
        client = GitHubClient()

        with self._patched(spawn_log, http):
            self.assertEqual(client.fetch_notifications(), [])

        self.assertEqual(len(spawn_log), 1)
        self.assertIn("token", spawn_log[0])
        args, kwargs = http.request.call_args
        self.assertEqual(
            args[:2], ("GET", "https://api.github.com/notifications?per_page=100")
        )
        self.assertEqual(kwargs["headers"]["Authorization"], f"bearer {self.TOKEN}")

    def test_the_token_is_minted_once_for_the_life_of_the_client(self):
        spawn_log: list = []
        http = mock.Mock()
        http.request.return_value = self._response()
        client = GitHubClient()

        with self._patched(spawn_log, http):
            client.fetch_notifications()
            client.mark_read("1")

        self.assertEqual(len(spawn_log), 1)
        self.assertEqual(http.request.call_count, 2)

    def test_an_unusable_token_falls_back_to_gh(self):
        for output in ("", "{}", "not-a-token", "gh: not logged in"):
            with self.subTest(output=output):
                http = mock.Mock()
                spawn_log: list = []

                def _run(cmd, timeout=None, check=False):
                    spawn_log.append(list(cmd))
                    return (0, output if "token" in cmd else "[]", "", None)

                with (
                    mock.patch.object(
                        functions_module, "_spawn_and_wait", side_effect=_run
                    ),
                    mock.patch.object(
                        tray_client_module, "get_http_client", return_value=http
                    ),
                ):
                    self.assertEqual(GitHubClient().fetch_notifications(), [])

                http.request.assert_not_called()
                self.assertEqual(spawn_log[-1][:2], ["gh", "api"])

    def test_a_rejected_token_is_reminted_once_then_falls_back(self):
        spawn_log: list = []
        http = mock.Mock()
        http.request.return_value = self._response(status=401)
        client = GitHubClient()

        with self._patched(spawn_log, http):
            self.assertEqual(client.fetch_notifications(), [])

        # One remint, then the gh fallback: never an unbounded retry loop.
        self.assertEqual(len(spawn_log), 3)
        self.assertIn("token", spawn_log[1])
        self.assertEqual(spawn_log[2][:2], ["gh", "api"])
        self.assertEqual(http.request.call_count, 2)

    def test_an_api_error_through_the_pooled_client_is_reported(self):
        http = mock.Mock()
        http.request.return_value = self._response(status=403)

        with self._patched([], http), self.assertRaises(GitHubClientError) as ctx:
            GitHubClient().fetch_notifications()

        self.assertTrue(ctx.exception.needs_auth)

    def test_enterprise_hosts_get_their_own_api_base(self):
        http = mock.Mock()
        http.request.return_value = self._response()

        with self._patched([], http):
            GitHubClient(hostname="ghe.example.com").fetch_notifications()

        url = http.request.call_args[0][1]
        self.assertEqual(
            url, "https://ghe.example.com/api/v3/notifications?per_page=100"
        )


class _RefreshButtonHarness:
    """Real button construction with the GTK component replaced by a recorder."""

    _refresh_button = tray_popover.GitHubTrayPopoverContent._refresh_button

    def __init__(self, loading):
        self.tray_widget = mock.Mock(loading=loading)


class RefreshButtonTests(unittest.TestCase):
    """The refresh control shows it is working instead of looking inert."""

    def _build(self, loading):
        recorded: dict = {}

        def _fake(icon=None, tooltip=None, style_classes=None, on_clicked=None, **_):
            recorded.update(icon=icon, tooltip=tooltip, style_classes=style_classes)
            if on_clicked is not None:
                on_clicked()
            return mock.Mock()

        harness = _RefreshButtonHarness(loading)
        with mock.patch.object(tray_popover, "ActionIconButton", _fake):
            harness._refresh_button()
        return recorded, harness

    def test_the_button_is_idle_when_nothing_is_in_flight(self):
        recorded, _ = self._build(loading=False)

        self.assertEqual(recorded["icon"], tray_state.glyph("refresh"))
        self.assertEqual(recorded["style_classes"], "")

    def test_the_button_shows_a_spinner_while_fetching(self):
        recorded, _ = self._build(loading=True)

        self.assertEqual(recorded["icon"], tray_state.glyph("spinner"))
        self.assertEqual(recorded["style_classes"], "busy")

    def test_the_button_still_triggers_a_manual_refresh(self):
        _, harness = self._build(loading=True)

        harness.tray_widget.refresh.assert_called_once_with(manual=True)

    def test_loading_participates_in_the_render_key(self):
        """Otherwise the spinner would not appear until something else changed."""
        harness = _RenderKeyHarness()
        harness.tray_widget.notifications = [{"id": "1", "reason": "mention"}]
        first = harness._render_key()

        harness.tray_widget.loading = True

        self.assertNotEqual(first, harness._render_key())


class _DetailHarness:
    """Real detail-load bookkeeping; the client and the GTK push are stubbed."""

    load_details = GitHubTrayWidget.load_details
    reset_detail = GitHubTrayWidget.reset_detail
    _apply_detail = GitHubTrayWidget._apply_detail
    _friendly_error = GitHubTrayWidget._friendly_error

    def __init__(self):
        self.detail = {
            "kind": None,
            "repo": None,
            "items": [],
            "pending": False,
            "error": "",
        }
        self._detail_generation = 0
        self._client = mock.Mock()
        self.config = {"workflow_runs_max": 10}
        self.pushes = 0

    def _push_state(self):
        self.pushes += 1


def _synchronous_worker():
    """Run the loader body inline and its idle callback immediately."""
    return (
        mock.patch.object(tray_module.helpers, "run_in_thread", lambda func: func),
        mock.patch.object(
            tray_module, "idle_add", side_effect=lambda callback, *args: callback(*args)
        ),
    )


class DetailGenerationTests(unittest.TestCase):
    """A ``gh`` call can outlive the view that asked for it."""

    def setUp(self):
        self.repo_a = {"full_name": "octo/a"}
        self.repo_b = {"full_name": "octo/b"}
        self.stale = [{"number": 1, "title": "A's issue"}]
        self.harness = _DetailHarness()
        self.harness._client.fetch_repo_items.side_effect = lambda full_name: {
            "issues": [],
            "pulls": [{"repo": full_name}],
        }
        inline, idle = _synchronous_worker()
        inline.start()
        self.addCleanup(inline.stop)
        idle.start()
        self.addCleanup(idle.stop)

    def test_a_late_reply_for_the_previous_repo_is_dropped(self):
        self.harness.load_details(self.repo_a, "issues")
        self.harness.load_details(self.repo_b, "pulls")

        self.harness._apply_detail(1, "issues", self.repo_a, self.stale, None)

        self.assertEqual("pulls", self.harness.detail["kind"])
        self.assertEqual(self.repo_b, self.harness.detail["repo"])
        self.assertEqual([{"repo": "octo/b"}], self.harness.detail["items"])
        self.assertNotIn(self.stale, self.harness.detail["items"])

    def test_a_late_error_for_the_previous_repo_is_dropped(self):
        self.harness.load_details(self.repo_a, "issues")
        self.harness.load_details(self.repo_b, "pulls")

        self.harness._apply_detail(1, "issues", self.repo_a, None, OSError("boom"))

        self.assertEqual("pulls", self.harness.detail["kind"])
        self.assertEqual("", self.harness.detail["error"])

    def test_going_back_drops_the_in_flight_load(self):
        self.harness.load_details(self.repo_a, "issues")

        self.harness.reset_detail()
        self.harness._apply_detail(1, "issues", self.repo_a, self.stale, None)

        self.assertIsNone(self.harness.detail["kind"])
        self.assertEqual([], self.harness.detail["items"])

    def test_the_current_load_still_applies(self):
        self.harness.load_details(self.repo_a, "issues")

        self.harness._apply_detail(
            self.harness._detail_generation, "issues", self.repo_a, self.stale, None
        )

        self.assertEqual(self.stale, self.harness.detail["items"])
        self.assertFalse(self.harness.detail["pending"])

    def test_a_failure_is_recorded_on_the_current_load(self):
        self.harness.load_details(self.repo_a, "workflows")

        self.harness._apply_detail(
            self.harness._detail_generation,
            "workflows",
            self.repo_a,
            None,
            OSError("gh: not logged in"),
        )

        self.assertIn("not logged in", self.harness.detail["error"])


class _DetailViewHarness:
    """Borrows the real detail renderer; the widget tree is recorded instead."""

    _render_detail = tray_detail.DetailView._render_detail

    def __init__(self, detail):
        self.tray_widget = mock.Mock(
            detail=detail, web_base="https://github.com", hide_popover=mock.Mock()
        )

    def _detail_browser_url(self, repo, kind):
        return "https://github.com"

    def _back_to_main(self):
        return None

    def _build_item_cards(self, _items, _kind):
        return [mock.Mock(name="item-card")]

    def _build_run_cards(self, _runs):
        return [mock.Mock(name="run-card")]


class DetailErrorRenderTests(unittest.TestCase):
    """A failed ``gh`` call must not read as an empty repo."""

    def _render(self, detail):
        harness = _DetailViewHarness(detail)
        built: dict[str, list] = {}

        def _recorder(name):
            def _build(*args, **kwargs):
                built.setdefault(name, []).append(kwargs)
                return mock.Mock(name=name)

            return _build

        with mock.patch.multiple(
            tray_detail,
            ActionIconButton=_recorder("ActionIconButton"),
            vbox=_recorder("vbox"),
            hbox=_recorder("hbox"),
            make_label=_recorder("make_label"),
            EmptyState=_recorder("EmptyState"),
            SkeletonRow=_recorder("SkeletonRow"),
        ):
            harness._render_detail()
        return built

    def _detail(self, **overrides):
        detail = {
            "kind": "issues",
            "repo": {"full_name": "octo/a"},
            "items": [],
            "pending": False,
            "error": "",
        }
        detail.update(overrides)
        return detail

    def test_a_detail_error_is_rendered(self):
        built = self._render(
            self._detail(error="GitHub is not reachable - run `gh auth login` first.")
        )

        self.assertEqual(1, len(built["EmptyState"]))
        self.assertEqual(
            "GitHub is not reachable - run `gh auth login` first.",
            built["EmptyState"][0]["subtitle"],
        )
        self.assertNotIn("SkeletonRow", built)

    def test_a_pending_load_still_shows_the_skeleton(self):
        built = self._render(self._detail(pending=True, error="stale"))

        self.assertEqual(1, len(built["SkeletonRow"]))
        self.assertNotIn("EmptyState", built)

    def test_an_empty_repo_is_still_the_empty_state(self):
        built = self._render(self._detail())

        self.assertEqual(1, len(built["EmptyState"]))
        self.assertEqual("No open issues", built["EmptyState"][0]["title"])


class _AvatarHarness:
    """Real avatar scheduling; the HTTP fetch and the pixbuf are stubbed."""

    _load_avatar_async = GitHubTrayWidget._load_avatar_async
    _apply_avatar = GitHubTrayWidget._apply_avatar

    def __init__(self, avatar_url=""):
        self.config = {"avatar_size": 44}
        self.user = {"avatar_url": avatar_url} if avatar_url else {}
        self.avatar_pixbuf = None
        self._avatar_url = ""
        self.pushes = 0

    def _push_state(self):
        self.pushes += 1


class AvatarFetchGuardTests(unittest.TestCase):
    """The same avatar URL must not be re-downloaded on every refresh."""

    def setUp(self):
        self.fetched: list[tuple] = []

        def _recording_thread(func):
            def _wrapper(*args):
                self.fetched.append(args)
                return None

            return _wrapper

        patcher = mock.patch.object(
            tray_module.helpers, "run_in_thread", _recording_thread
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_unchanged_avatar_url_is_not_refetched(self):
        widget = _AvatarHarness("https://avatars.example/octo.png")

        widget._load_avatar_async()
        widget._load_avatar_async()

        self.assertEqual([("https://avatars.example/octo.png", 44)], self.fetched)

    def test_a_changed_avatar_url_is_refetched(self):
        widget = _AvatarHarness("https://avatars.example/octo.png")
        widget._load_avatar_async()

        widget.user = {"avatar_url": "https://avatars.example/octo-2.png"}
        widget._load_avatar_async()

        self.assertEqual(2, len(self.fetched))
        self.assertEqual("https://avatars.example/octo-2.png", self.fetched[-1][0])

    def test_a_user_without_an_avatar_fetches_nothing(self):
        widget = _AvatarHarness()

        widget._load_avatar_async()

        self.assertEqual([], self.fetched)

    def test_a_failed_download_may_be_retried(self):
        widget = _AvatarHarness("https://avatars.example/octo.png")
        widget._load_avatar_async()

        widget._apply_avatar(None)
        widget._load_avatar_async()

        self.assertEqual(2, len(self.fetched))

    def test_a_loaded_pixbuf_is_published(self):
        widget = _AvatarHarness()
        pixbuf = mock.Mock()

        widget._apply_avatar(pixbuf)

        self.assertIs(pixbuf, widget.avatar_pixbuf)
        self.assertEqual(1, widget.pushes)


class _LocalPathHarness:
    """Real local-project lookup; the config is the only input."""

    local_mappings = GitHubTrayWidget.local_mappings
    repo_local_path = GitHubTrayWidget.repo_local_path
    _mappings_text = GitHubTrayWidget._mappings_text

    def __init__(self, projects):
        self.config = {"local_projects": projects}


class LocalMappingTests(unittest.TestCase):
    """One parse per render, not one per repo card."""

    def _repos(self):
        return [{"full_name": f"octo/repo{index}"} for index in range(20)]

    def _projects(self):
        return {f"octo/repo{index}": f"/src/repo{index}" for index in range(20)}

    def test_the_mappings_are_parsed_once_per_render(self):
        harness = _LocalPathHarness(self._projects())

        with mock.patch.object(
            tray_state,
            "parse_local_projects",
            wraps=tray_state.parse_local_projects,
        ) as parse:
            mappings = harness.local_mappings()
            paths = [harness.repo_local_path(repo, mappings) for repo in self._repos()]

        self.assertEqual(1, parse.call_count)
        self.assertEqual("/src/repo0", paths[0])
        self.assertEqual("/src/repo19", paths[19])

    def test_the_omitted_argument_still_parses_and_expands(self):
        harness = _LocalPathHarness({"octo/home": "~/src/home"})

        path = harness.repo_local_path({"full_name": "octo/home"})

        self.assertEqual(os.path.expanduser("~/src/home"), path)

    def test_an_unmapped_repo_has_no_local_path(self):
        harness = _LocalPathHarness({"octo/a": "/src/a"})

        self.assertEqual("", harness.repo_local_path({"full_name": "octo/b"}))


class RepoCardMappingTests(unittest.TestCase):
    """The card builder receives the parsed mappings instead of re-parsing."""

    def test_the_cards_are_given_one_pre_parsed_mapping(self):
        recorded: dict = {}

        def _fake_cards(_self, repos, username, mappings):
            recorded.update(repos=repos, username=username, mappings=mappings)
            return []

        with mock.patch.object(tray_repos.ReposView, "_build_repo_cards", _fake_cards):
            harness = mock.Mock()
            harness.user = {"login": "octo"}
            harness.repos = [{"full_name": "octo/a", "pushed_at": ""}]
            harness.local_mappings.return_value = {"octo/a": "/src/a"}
            view = tray_repos.ReposView()
            view.tray_widget = harness
            view.config = {"max_repos": 5, "sort_by": "updated"}

            view._build_repos()

        harness.local_mappings.assert_called_once_with()
        self.assertEqual({"octo/a": "/src/a"}, recorded["mappings"])
        self.assertEqual("octo", recorded["username"])


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the GitHub tray helpers (pure logic, no display/gh)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from utils import functions as functions_module
from widgets.github_tray import state as tray_state
from widgets.github_tray import widget as tray_module
from widgets.github_tray.client import GitHubClient, GitHubClientError
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

    def __init__(self, config, notifications=()):
        self.config = config
        self._client = mock.Mock(web_base="https://github.com")
        self._generation = 1
        self._busy = True
        self.loading = False
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

    def __init__(self, content, visible=False):
        self._popup = _StubPopover(content, visible)
        self._popover_built = True
        self.badge_label = mock.Mock()
        self.tooltips_enabled = False
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

    _render_key = tray_module.GitHubTrayPopoverContent._render_key

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


class ClientTests(unittest.TestCase):
    """gh CLI command construction and error mapping."""

    def _patch_run(self, payload, returncode=0, stderr=""):
        stdout = json.dumps(payload) if payload is not None else ""
        result = (returncode, stdout, stderr, None)
        # the client delegates to functions.run_command -> _spawn_and_wait
        return mock.patch.object(
            functions_module, "_spawn_and_wait", return_value=result
        )

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
        first, second = run.call_args_list
        self.assertIn("PATCH", first[0][0])
        self.assertIn("notifications/threads/123", first[0][0])
        self.assertIn("POST", second[0][0])
        self.assertIn("repos/o/r/actions/runs/9/rerun-failed-jobs", second[0][0])

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


if __name__ == "__main__":
    unittest.main()

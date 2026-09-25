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
from widgets.github_tray.client import GitHubClient, GitHubClientError


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


class ClientTests(unittest.TestCase):
    """gh CLI command construction and error mapping."""

    def _patch_run(self, payload, returncode=0, stderr=""):
        proc = mock.Mock()
        proc.returncode = returncode
        proc.stdout = json.dumps(payload) if payload is not None else ""
        proc.stderr = stderr
        # the client delegates to functions.run_command, which wraps subprocess.run
        return mock.patch.object(functions_module.subprocess, "run", return_value=proc)

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

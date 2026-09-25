"""Pure helpers for the GitHub tray widget: display formatting, notification
semantics, repository sorting, mapping parsing and alert diffing.

"""

from __future__ import annotations

import json
import os
from concurrent.futures import Future
from datetime import datetime, timezone

from utils.decorators import thread
from utils.functions import ensure_directory, read_json_file, write_json_file

# Nerd Font (Material Design) glyphs referenced by codepoint so they survive
# editors/tooling that strip private-use characters.
_ICONS = {
    "github": 0xF02A4,
    "star": 0xF04CE,
    "fork": 0xF062D,
    "pull": 0xF0632,
    "merge": 0xF062F,
    "branch": 0xF062C,
    "commit": 0xF0718,
    "repo": 0xF00BA,
    "issue": 0xF001A,
    "issue_closed": 0xF05E1,
    "tag": 0xF04FA,
    "shield": 0xF0498,
    "discussion": 0xF0369,
    "folder": 0xF024B,
    "folder_open": 0xF0770,
    "editor": 0xF018D,
    "code": 0xF0169,
    "draft": 0xF03EB,
    "clock": 0xF051F,
    "lock": 0xF033E,
    "bell": 0xF009A,
    "play": 0xF040A,
    "check": 0xF012C,
    "refresh": 0xF0450,
    "gear": 0xF0493,
    "open_link": 0xF03CC,
    "error": 0xF0026,
    "info": 0xF02FD,
    "back": 0xF0141,
    "forward": 0xF0142,
    "eye": 0xF0208,
    "eye_off": 0xF0209,
    "account": 0xF0004,
    "mention": 0xF0065,
    "plus": 0xF0415,
    "trash": 0xF01B4,
    "spinner": 0xF0996,
    "failure": 0xF0156,
    "cancelled": 0xF073A,
    "skipped": 0xF04AD,
}


def glyph(name: str) -> str:
    """Return the Nerd Font glyph for a named icon ('' for unknown names)."""
    return chr(_ICONS[name]) if name in _ICONS else ""


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def relative_time(value: str | None) -> str:
    """Compact '3h ago' style age string from an ISO-8601 timestamp."""
    parsed = _parse_dt(value)
    if parsed is None:
        return ""
    seconds = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 2592000:
        return f"{seconds // 86400}d ago"
    if seconds < 31536000:
        return f"{seconds // 2592000}mo ago"
    return f"{seconds // 31536000}y ago"


def format_count(value: int | str | None) -> str:
    """Format a count the way GitHub does: 1.2k / 3.4M."""
    number = int(value or 0)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}".rstrip("0").rstrip(".") + "k"
    return str(number)


def workflow_duration(run: dict) -> str:
    """Human duration of a workflow run ('5m 12s', '1h 4m', ...)."""
    start = _parse_dt(run.get("run_started_at") if run else None)
    if start is None:
        return ""
    end_value = run.get("updated_at") if run.get("status") == "completed" else None
    end = _parse_dt(end_value) or datetime.now(timezone.utc)
    seconds = max(0, int((end - start).total_seconds()))
    minutes = seconds // 60
    if minutes >= 60:
        return f"{minutes // 60}h {minutes % 60}m"
    return (f"{minutes}m " if minutes > 0 else "") + f"{seconds % 60}s"


def notification_type(item: dict) -> str:
    subject = item.get("subject") if item else None
    return str(subject.get("type") or "") if subject else ""


def notification_state(item: dict) -> str:
    """State pill text: Open/Merged/Draft/Closed ('' when unknown)."""
    info = item.get("_stateInfo") if item else None
    if not info:
        return ""
    if info.get("isDraft"):
        return "Draft"
    state = str(info.get("state") or "").lower()
    return state.capitalize() if state else ""


def notification_icon(item: dict) -> str:
    """Glyph for a notification card based on its subject type/state."""
    kind = notification_type(item)
    info = item.get("_stateInfo") if item else None
    if kind == "Issue" or kind == "IssueComment":
        closed = bool(info) and info.get("state") == "CLOSED"
        return glyph("issue_closed" if closed else "issue")
    if kind.startswith("PullRequest"):
        return glyph("merge" if info and info.get("state") == "MERGED" else "pull")
    if kind == "Commit":
        return glyph("commit")
    if kind == "Release":
        return glyph("tag")
    if kind == "Discussion":
        return glyph("discussion")
    if kind == "SecurityAlert":
        return glyph("shield")
    if kind == "CheckSuite":
        return glyph("play")
    return glyph("bell")


_REASONS = {
    "assign": "Assigned",
    "author": "Author",
    "comment": "Comment",
    "ci_activity": "CI activity",
    "invitation": "Invitation",
    "manual": "Subscribed",
    "mention": "Mentioned",
    "review_requested": "Review requested",
    "security_alert": "Security",
    "state_change": "State change",
    "subscribed": "Watching",
    "team_mention": "Team mention",
    "approval_requested": "Approval requested",
    "member_feature_requested": "Feature request",
}


def reason_label(reason: str | None) -> str:
    return _REASONS.get(str(reason or ""), str(reason or "").replace("_", " "))


def workflow_status(run: dict) -> str:
    status = run.get("status")
    conclusion = run.get("conclusion")
    if status == "in_progress":
        return "Running"
    if status in ("queued", "waiting", "pending"):
        return "Queued"
    if conclusion == "success":
        return "Success"
    if conclusion == "failure":
        return "Failed"
    if conclusion == "cancelled":
        return "Cancelled"
    if conclusion == "skipped":
        return "Skipped"
    if conclusion == "timed_out":
        return "Timed out"
    return conclusion or status or "Completed"


def workflow_icon(run: dict) -> str:
    status = run.get("status")
    conclusion = run.get("conclusion")
    if status != "completed":
        return glyph("spinner")
    if conclusion == "success":
        return glyph("check")
    if conclusion in ("failure", "timed_out"):
        return glyph("failure")
    if conclusion == "cancelled":
        return glyph("cancelled")
    return glyph("skipped")


def run_tint(run: dict) -> str:
    """Semantic colour class for a workflow run's icon (status is already
    conveyed by the pill text + glyph, the tint only reinforces it).

    Returns one of ``"running"``, ``"success"``, ``"failure"`` or ``""``
    (neutral — queued/skipped/cancelled read as muted, like GitHub).
    """
    status = run.get("status")
    conclusion = run.get("conclusion")
    if status != "completed":
        return "running"
    if conclusion == "success":
        return "success"
    if conclusion in ("failure", "timed_out"):
        return "failure"
    return ""


_LANGUAGE_COLORS = {
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Python": "#3572A5",
    "Rust": "#dea584",
    "Go": "#00ADD8",
    "C": "#555555",
    "C++": "#f34b7d",
    "C#": "#178600",
    "Java": "#b07219",
    "Kotlin": "#A97BFF",
    "Swift": "#F05138",
    "Ruby": "#701516",
    "PHP": "#4F5D95",
    "Shell": "#89e051",
    "HTML": "#e34c26",
    "CSS": "#663399",
    "SCSS": "#c6538c",
    "Dart": "#00B4AB",
    "Lua": "#000080",
    "Vue": "#41b883",
    "Svelte": "#ff3e00",
    "Elixir": "#6e4a7e",
    "Haskell": "#5e5086",
    "Zig": "#ec915c",
    "Nix": "#7e7eff",
    "Dockerfile": "#384d54",
    "Makefile": "#427819",
    "Scala": "#c22d40",
    "Perl": "#0298c3",
    "R": "#198CE7",
    "Jupyter Notebook": "#DA5B0B",
    "Astro": "#ff5a03",
    "Markdown": "#083fa1",
}


def language_color(language: str | None, fallback: str) -> str:
    return _LANGUAGE_COLORS.get(str(language or ""), fallback)


# --------------------------------------------------------------------------- #
# Repositories
# --------------------------------------------------------------------------- #

_SORT_KEYS = {
    "stars": lambda repo: repo.get("stargazers_count") or 0,
    "name": lambda repo: (repo.get("name") or "").lower(),
    "created": lambda repo: repo.get("created_at") or "",
    "pushed": lambda repo: repo.get("pushed_at") or "",
    "updated": lambda repo: repo.get("updated_at") or "",
}


def sort_repos(
    repos: list[dict], sort_by: str, sort_order: str, max_repos: int | None = None
) -> list[dict]:
    """Sort repos like the reference: default 'updated' descending."""
    key = _SORT_KEYS.get(str(sort_by).lower(), _SORT_KEYS["updated"])
    sorted_repos = sorted(repos, key=key, reverse=str(sort_order) != "asc")
    if max_repos:
        return sorted_repos[:max_repos]
    return sorted_repos


def is_own_repo(repo: dict, username: str) -> bool:
    owner = repo.get("owner") or {}
    return not owner or owner.get("login") == username


def filter_own_repos(
    repos: list[dict], username: str, enabled: bool = False
) -> list[dict]:
    """Repos to display; with ``enabled`` keep only repos owned by the user
    and drop organization/collaborator ones."""
    if not enabled:
        return repos
    return [repo for repo in repos if is_own_repo(repo, username)]


def sort_label(sort_by: str, sort_order: str) -> str:
    label_map = {
        "updated": "by update",
        "pushed": "by push",
        "created": "by creation",
        "stars": "by stars",
        "name": "by name",
    }
    text = "· " + label_map.get(str(sort_by), str(sort_by))
    return text + (" ↑" if str(sort_order) == "asc" else " ↓")


# --------------------------------------------------------------------------- #
# Notification web URLs
# --------------------------------------------------------------------------- #


def web_notification_url(item: dict, web_base: str) -> str:
    """Turn an API notification subject/repository URL into a browsable one."""
    subject = item.get("subject") or {}
    subject_url = str(subject.get("url") or "")
    repo = item.get("repository") or {}
    if subject_url:
        if "/api/v3/" in subject_url or "api.github.com/" in subject_url:
            api_part = (
                subject_url.split("/api/v3/", 1)[1]
                if "/api/v3/" in subject_url
                else subject_url.split("api.github.com/", 1)[1]
            )
            if api_part.startswith("repos/"):
                subject_url = web_base + "/" + api_part[len("repos/") :]
        if str(subject.get("type") or "").startswith("PullRequest"):
            subject_url = subject_url.replace("/pulls/", "/pull/").replace(
                "/issues/", "/pull/"
            )
        return subject_url
    return repo.get("html_url") or f"{web_base}/notifications"


# --------------------------------------------------------------------------- #
# Local project mappings
# --------------------------------------------------------------------------- #


def parse_local_projects(text: str) -> dict:
    try:
        data = json.loads(text or "{}")
        if isinstance(data, dict):
            return data
    except (TypeError, ValueError):
        pass
    return {}


def expand_home(path: str, home: str) -> str:
    value = str(path or "").strip()
    if value == "~":
        return home
    if value.startswith("~/"):
        return home + value[1:]
    return value


def local_path(mappings_text: str, full_name: str, home: str) -> str:
    return expand_home(parse_local_projects(mappings_text).get(full_name, ""), home)


def sorted_mappings(mappings_text: str) -> list[dict]:
    return [
        {"repo": repo, "path": path}
        for repo, path in sorted(parse_local_projects(mappings_text).items())
    ]


# --------------------------------------------------------------------------- #
# State cache & alert diffing
# --------------------------------------------------------------------------- #


def load_state_file(path: str) -> dict:
    data = read_json_file(path)
    return data if isinstance(data, dict) else {}


def _write_state_file(path: str, data: dict) -> None:
    try:
        # Both calls must complete before returning: callers await this future
        # and then read the file back, and this already runs on a worker
        # thread, so off-thread writes would race the read.
        ensure_directory(os.path.dirname(path), sync=True)
        write_json_file(path, data, sync=True)
    except OSError:
        pass


def save_state_file(path: str, data: dict) -> Future[None]:
    """Queue a state write on the thread pool so callers never block on disk."""
    return thread(_write_state_file, path, data)


def save_menu_cache(path: str, payload: dict, now: float | None = None) -> Future[None]:
    """Persist a menu payload (profile + repos) tagged with the current time."""
    import time

    if now is None:
        now = time.time()
    return save_state_file(path, {"cached_at": now, "payload": payload})


def read_menu_cache(
    path: str, ttl: int, now: float | None = None
) -> tuple[dict, float] | None:
    """Return ``(payload, age_seconds)`` when a menu cache file exists and is
    younger than ``ttl`` seconds, otherwise ``None``. A ``ttl`` of ``0`` or
    less disables the cache entirely."""
    import time

    if ttl <= 0:
        return None
    if now is None:
        now = time.time()
    data = load_state_file(path)
    cached_at = data.get("cached_at")
    if not isinstance(cached_at, (int, float)):
        return None
    age = now - float(cached_at)
    if age < 0 or age >= ttl:
        return None
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None
    return payload, age


def _repos_by_id(repos: list[dict]) -> dict[str, dict]:
    return {str(repo.get("id")): repo for repo in repos if repo.get("id")}


def diff_alerts(previous: dict, current: dict, flags: dict) -> list[tuple[str, str]]:
    """Compare a previous state snapshot with the current one and return
    ``(title, body)`` desktop-alert pairs for everything that changed,
    honouring the boolean ``flags`` dict (stars/forks/issues/followers/
    notifications/workflow_*)."""
    alerts: list[tuple[str, str]] = []
    if not previous:
        return alerts

    old_repos = _repos_by_id(previous.get("repos", []))
    for field, title, suffix in (
        ("stargazers_count", "New Stars!", "⭐"),
        ("open_issues_count", "New Issues Opened", "issues"),
        ("forks_count", "New Forks Created", "forks"),
    ):
        flag = {
            "stargazers_count": "stars",
            "open_issues_count": "issues",
            "forks_count": "forks",
        }[field]
        if not flags.get(flag, True):
            continue
        changes = []
        for repo in current.get("repos", []):
            old = old_repos.get(str(repo.get("id")))
            old_count = (old or {}).get(field, repo.get(field)) or 0
            diff = int(repo.get(field) or 0) - int(old_count)
            if diff > 0:
                changes.append(f"{repo.get('name')} +{diff} {suffix}")
        if changes:
            alerts.append((title, "\n".join(changes)))

    if flags.get("followers", True):
        old_followers = {str(f.get("id")) for f in previous.get("followers", [])}
        new_followers = [
            f
            for f in current.get("followers", [])
            if str(f.get("id")) not in old_followers
        ]
        if new_followers:
            if len(new_followers) == 1:
                name = new_followers[0].get("login") or "someone"
                alerts.append(("New Followers", name))
            else:
                alerts.append(("New Followers", f"+{len(new_followers)} followers"))

    if flags.get("notifications", True):
        old_ids = {str(n.get("id")) for n in previous.get("notifications", [])}
        fresh = [
            n
            for n in current.get("notifications", [])
            if str(n.get("id")) not in old_ids
        ]
        if fresh:
            count = len(fresh)
            alerts.append(
                (
                    "GitHub Notifications",
                    f"{count} new notification" + ("" if count == 1 else "s"),
                )
            )

    workflow_flags = {
        "started": flags.get("workflow_started", True),
        "success": flags.get("workflow_success", True),
        "failure": flags.get("workflow_failure", True),
        "cancelled": flags.get("workflow_cancelled", True),
    }
    previous_workflows = previous.get("workflows", {}) or {}
    for full_name, runs in (current.get("workflows", {}) or {}).items():
        old_runs = {str(r.get("id")): r for r in previous_workflows.get(full_name, [])}
        repo_name = full_name.rsplit("/", 1)[-1]
        for run in runs:
            before = old_runs.get(str(run.get("id")))
            run_name = run.get("name") or "Workflow"
            category = f"{repo_name} • {run_name}"
            if (
                not before
                and run.get("status") == "in_progress"
                and workflow_flags["started"]
            ):
                alerts.append(
                    (
                        "GitHub Actions: Workflow Started",
                        category + "\n" + str(run.get("head_branch") or ""),
                    )
                )
            elif (
                before
                and before.get("status") != run.get("status")
                and run.get("status") == "completed"
            ):
                conclusion = run.get("conclusion")
                if conclusion == "success" and workflow_flags["success"]:
                    alerts.append(("GitHub Actions: Workflow Succeeded", category))
                elif conclusion == "failure" and workflow_flags["failure"]:
                    alerts.append(("GitHub Actions: Workflow Failed", category))
                elif conclusion == "cancelled" and workflow_flags["cancelled"]:
                    alerts.append(("GitHub Actions: Workflow Cancelled", category))

    return alerts

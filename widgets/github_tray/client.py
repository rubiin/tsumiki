"""GitHub API access for the GitHub tray widget."""

from __future__ import annotations

import json
import re

from utils.functions import CommandError, run_command

_NOTIFICATION_RE = re.compile(r"/repos/([^/]+)/([^/]+)/(issues|pulls)/(\d+)$")


class GitHubClientError(Exception):
    """Raised when a gh call fails; ``needs_auth`` marks auth problems."""

    def __init__(self, message: str, needs_auth: bool = False):
        super().__init__(message)
        self.needs_auth = needs_auth


class GitHubClient:
    """Thin, synchronous wrapper around the gh CLI."""

    def __init__(self, hostname: str = "", timeout: float = 30):
        self.hostname = str(hostname or "").strip().rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    # plumbing
    # ------------------------------------------------------------------ #
    @property
    def web_base(self) -> str:
        return f"https://{self.hostname}" if self.hostname else "https://github.com"

    def _command(self, args: list[str]) -> list[str]:
        cmd = ["gh", *args]
        if self.hostname:
            # gh api accepts --hostname for hosts added via `gh auth login`.
            cmd.extend(["--hostname", self.hostname])
        return cmd

    def _run(self, args: list[str]) -> dict | list:
        try:
            output = run_command(
                self._command(args), timeout=self.timeout, check=True
            )
        except CommandError as e:
            if e.kind == "missing":
                raise GitHubClientError(
                    "The GitHub CLI (`gh`) is not installed", needs_auth=False
                ) from None
            if e.kind == "timeout":
                raise GitHubClientError("The GitHub CLI timed out") from None
            message = self._error_message(e.stderr)
            raise GitHubClientError(
                message, needs_auth=self._looks_like_auth(message)
            ) from None

        if not output.strip():
            return {}
        try:
            return json.loads(output)
        except ValueError:
            raise GitHubClientError("The GitHub CLI returned invalid JSON") from None

    @staticmethod
    def _error_message(stderr: str) -> str:
        text = (stderr or "").strip()
        if not text:
            return "The GitHub CLI reported an error"
        # gh api prints its HTTP-error payload to stderr.
        message = text
        with_gh = text
        if ":" in text:
            # "gh: HTTP 401 Unauthorized (message)" -> keep the human part.
            with_gh = text.split("gh: ", 1)[-1]
        try:
            payload = json.loads(with_gh)
            if isinstance(payload, dict) and payload.get("message"):
                message = payload["message"]
        except (ValueError, TypeError):
            message = with_gh
        return message[:400]

    @staticmethod
    def _looks_like_auth(message: str) -> bool:
        lowered = message.lower()
        return any(
            token in lowered
            for token in (
                "not logged in",
                "bad credentials",
                "authentication required",
                "401",
                "403",
                "could not read username",
                "auth",
            )
        )

    def _graphql(self, query: str) -> dict:
        data = self._run(["api", "graphql", "-f", f"query={query}"])
        if isinstance(data, dict) and data.get("errors") and not data.get("data"):
            error = data["errors"][0]
            message = error.get("message", "GraphQL error")
            raise GitHubClientError(str(message))
        return data.get("data", {}) if isinstance(data, dict) else {}

    # ------------------------------------------------------------------ #
    # menu payload (profile + repositories + followers + notifications)
    # ------------------------------------------------------------------ #
    MENU_QUERY = """
query {
  viewer {
    login
    avatarUrl
    followers(first: 1) { totalCount }
    repositories(
      first: 100
      ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      totalCount
      nodes {
        databaseId
        name
        nameWithOwner
        description
        url
        isPrivate
        isFork
        owner { login }
        parent { url }
        primaryLanguage { name }
        stargazerCount
        forkCount
        updatedAt
        pushedAt
        createdAt
        issues(states: OPEN) { totalCount }
        pullRequests(states: OPEN) { totalCount }
      }
    }
    followersList: followers(first: 100) { nodes { databaseId login url } }
  }
}
"""

    def fetch_menu(self, username_fallback: str = "") -> dict:
        """Profile, up-to-100 repos and followers in one GraphQL call."""
        viewer = self._graphql(self.MENU_QUERY).get("viewer") or {}
        repos = []
        for node in (viewer.get("repositories") or {}).get("nodes", []):
            issues = (node.get("issues") or {}).get("totalCount", 0)
            pulls = (node.get("pullRequests") or {}).get("totalCount", 0)
            parent = node.get("parent")
            repos.append(
                {
                    "id": node.get("databaseId"),
                    "name": node.get("name"),
                    "full_name": node.get("nameWithOwner"),
                    "description": node.get("description"),
                    "html_url": node.get("url"),
                    "private": node.get("isPrivate"),
                    "fork": node.get("isFork"),
                    "owner": node.get("owner"),
                    "parent": {"html_url": parent.get("url")} if parent else None,
                    "language": (node.get("primaryLanguage") or {}).get("name"),
                    "stargazers_count": node.get("stargazerCount", 0),
                    "forks_count": node.get("forkCount", 0),
                    "open_issues_count": issues + pulls,
                    "_issuesCount": issues,
                    "_pullsCount": pulls,
                    "updated_at": node.get("updatedAt"),
                    "pushed_at": node.get("pushedAt"),
                    "created_at": node.get("createdAt"),
                }
            )
        followers = [
            {
                "id": follower.get("databaseId"),
                "login": follower.get("login"),
                "html_url": follower.get("url"),
            }
            for follower in (viewer.get("followersList") or {}).get("nodes", [])
        ]
        return {
            "user": {
                "login": viewer.get("login") or username_fallback,
                "avatar_url": viewer.get("avatarUrl"),
                "followers": (viewer.get("followers") or {}).get("totalCount", 0),
                "public_repos": (viewer.get("repositories") or {}).get(
                    "totalCount", len(repos)
                ),
            },
            "repos": repos,
            "followers": followers,
            "web": self.web_base,
        }

    # ------------------------------------------------------------------ #
    # notifications
    # ------------------------------------------------------------------ #
    def fetch_notifications(self) -> list[dict]:
        """Unread notifications via the REST endpoint (gh session)."""
        data = self._run(["api", "notifications?per_page=100"])
        return data if isinstance(data, list) else []

    def enrich_notification_states(self, notifications: list[dict]) -> list[dict]:
        """Attach ``_stateInfo`` {state, isDraft} to Issue/PullRequest
        notifications with one aliased GraphQL query."""
        aliases: list[str] = []
        lookup: dict[str, dict] = {}
        for notification in notifications:
            subject = notification.get("subject") or {}
            match = _NOTIFICATION_RE.search(str(subject.get("url") or ""))
            if not match or subject.get("type") not in ("Issue", "PullRequest"):
                continue
            owner, repo, kind, number = match.groups()
            alias = "n" + "".join(c for c in str(notification["id"]) if c.isdigit())
            if not alias:
                continue
            lookup[alias] = notification
            field = "pullRequest" if kind == "pulls" else "issue"
            extras = " isDraft" if field == "pullRequest" else ""
            aliases.append(
                f"{alias}:repository(owner: {json.dumps(owner)}, "
                f"name: {json.dumps(repo)})"
                f"{{ {field}(number: {number}) {{ state{extras} }} }}"
            )
        if not aliases:
            return notifications
        try:
            data = self._graphql("{\n" + "\n".join(aliases) + "\n}")
        except GitHubClientError:
            return notifications
        for alias, notification in lookup.items():
            repo_node = data.get(alias) or {}
            item = repo_node.get("pullRequest") or repo_node.get("issue")
            if item:
                notification["_stateInfo"] = {
                    "state": item.get("state"),
                    "isDraft": item.get("isDraft", False),
                }
        return notifications

    # ------------------------------------------------------------------ #
    # detail payloads
    # ------------------------------------------------------------------ #
    # %-style placeholders on purpose: str.format/f-strings would choke on
    # the GraphQL braces.
    REPO_ITEMS_QUERY = """
query {
  repository(owner: %(owner)s, name: %(name)s) {
    issues(
      first: 20
      states: OPEN
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      nodes {
        databaseId
        number
        title
        url
        state
        updatedAt
        author { login }
        labels(first: 10) { nodes { name color } }
      }
    }
    pullRequests(
      first: 20
      states: OPEN
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      nodes {
        databaseId
        number
        title
        url
        state
        updatedAt
        isDraft
        author { login }
        labels(first: 10) { nodes { name color } }
      }
    }
  }
}
"""

    def fetch_repo_items(self, full_name: str) -> dict:
        """Open issues and pull requests of one repo (two lists)."""
        owner, name = full_name.split("/", 1)
        query = self.REPO_ITEMS_QUERY % {
            "owner": json.dumps(owner),
            "name": json.dumps(name),
        }
        repo = self._graphql(query).get("repository") or {}

        def shape(node: dict) -> dict:
            return {
                "id": node.get("databaseId"),
                "number": node.get("number"),
                "title": node.get("title"),
                "html_url": node.get("url"),
                "state": str(node.get("state") or "OPEN").lower(),
                "updated_at": node.get("updatedAt"),
                "user": node.get("author"),
                "labels": (node.get("labels") or {}).get("nodes", []),
                "draft": node.get("isDraft", False),
            }

        return {
            "issues": [
                shape(node) for node in (repo.get("issues") or {}).get("nodes", [])
            ],
            "pulls": [
                shape(node)
                for node in (repo.get("pullRequests") or {}).get("nodes", [])
            ],
        }

    def fetch_workflow_runs(self, full_name: str, limit: int = 10) -> list[dict]:
        data = self._run(["api", f"repos/{full_name}/actions/runs?per_page={limit}"])
        runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
        for run in runs:
            run["repository_full_name"] = full_name
        return runs

    def fetch_avatar_url(self) -> str:
        """Avatar of the authenticated user (REST), '' when unavailable."""
        data = self._run(["api", "user"])
        if isinstance(data, dict):
            return str(data.get("avatar_url") or "")
        return ""

    # ------------------------------------------------------------------ #
    # actions
    # ------------------------------------------------------------------ #
    def mark_read(self, thread_id: str) -> None:
        self._run(["api", "--method", "PATCH", f"notifications/threads/{thread_id}"])

    def rerun_failed_jobs(self, full_name: str, run_id: str) -> None:
        # GitHub accepts an empty POST body for this endpoint.
        self._run(
            [
                "api",
                "--method",
                "POST",
                f"repos/{full_name}/actions/runs/{run_id}/rerun-failed-jobs",
            ]
        )

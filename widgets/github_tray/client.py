"""GitHub API access for the GitHub tray widget.

REST goes through the shared pooled ``httpx`` client once a token has been
minted with ``gh auth token``; ``gh api`` remains the fallback when no token is
available, and carries every GraphQL call.
"""

from __future__ import annotations

import json
import re
import time

from fabric.utils import logger

from utils.functions import CommandError, get_http_client, run_command

from . import state as tray_state

_NOTIFICATION_RE = re.compile(r"/repos/([^/]+)/([^/]+)/(issues|pulls)/(\d+)$")
_ALIAS_CLEAN = re.compile(r"[^_0-9A-Za-z]")
# gh prints the raw token; anything else (empty, JSON, a usage error) is no token.
_TOKEN_RE = re.compile(r"^(gh[pousr]_[A-Za-z0-9]+|[0-9a-f]{40})$")


class GitHubClientError(Exception):
    """Raised when a gh call fails; ``needs_auth`` marks auth problems."""

    def __init__(self, message: str, needs_auth: bool = False):
        super().__init__(message)
        self.needs_auth = needs_auth


class _TokenExpiredError(Exception):
    """Raised internally when the pooled request is rejected as unauthorized."""


def _alias_for(notification: dict, taken: set[str]) -> str:
    """A GraphQL alias per notification: unique, and valid for any id shape.

    Thread ids are base64-ish (``MDM6...OQ==``), so ``"n" + digits`` collapsed
    digitless ids onto one alias and duplicated fields voided the whole query.
    """
    base = "n" + _ALIAS_CLEAN.sub("_", str(notification.get("id") or ""))
    if base == "n":
        base = "n0"
    alias, suffix = base, 2
    while alias in taken:
        alias, suffix = f"{base}_{suffix}", suffix + 1
    taken.add(alias)
    return alias


class GitHubClient:
    """Thin, synchronous wrapper around the GitHub API."""

    def __init__(self, hostname: str = "", timeout: float = 30):
        self.hostname = str(hostname or "").strip().rstrip("/")
        self.timeout = timeout
        self._token: str | None = None
        self._token_tried = False

    # -- plumbing --
    @property
    def web_base(self) -> str:
        return f"https://{self.hostname}" if self.hostname else "https://github.com"

    @property
    def api_base(self) -> str:
        if not self.hostname:
            return "https://api.github.com"
        return f"https://{self.hostname}/api/v3"

    def _command(self, args: list[str]) -> list[str]:
        cmd = ["gh", *args]
        if self.hostname:
            # gh api accepts --hostname for hosts added via `gh auth login`.
            cmd.extend(["--hostname", self.hostname])
        return cmd

    def _run(self, args: list[str]) -> dict | list:
        try:
            output = run_command(self._command(args), timeout=self.timeout, check=True)
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

    # -- transport: pooled HTTP with a bearer token, gh as the fallback --
    def _auth_token(self) -> str:
        """Mint a token once; the pooled client is only usable with one."""
        if self._token_tried:
            return self._token or ""
        self._token_tried = True
        output = run_command(self._command(["auth", "token"]), timeout=self.timeout)
        candidate = str(output or "").strip()
        if not _TOKEN_RE.match(candidate):
            logger.info(
                "[github_tray] no usable token from `gh auth token`; using gh api"
            )
            return ""
        self._token = candidate
        return self._token

    def _forget_token(self) -> None:
        # A rejected token may simply have expired; mint a fresh one next time.
        self._token = None
        self._token_tried = False

    def _rest_http(self, token: str, method: str, path: str) -> dict | list:
        url = f"{self.api_base}/{str(path).lstrip('/')}"
        headers = {
            "Authorization": f"bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            response = get_http_client().request(
                method, url, headers=headers, timeout=self.timeout
            )
        except Exception as error:
            raise GitHubClientError(f"Request to {path} failed: {error}") from None
        if response.status_code == 401:
            raise _TokenExpiredError
        if response.status_code >= 400:
            message = self._error_message(response.text)
            raise GitHubClientError(
                message, needs_auth=self._looks_like_auth(message)
            ) from None
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            raise GitHubClientError("GitHub returned invalid JSON") from None

    def _rest_gh(self, method: str, path: str) -> dict | list:
        args = ["api", path] if method == "GET" else ["api", "--method", method, path]
        return self._run(args)

    def _rest(self, method: str, path: str) -> dict | list:
        """REST through the pooled client, falling back to ``gh api``.

        ``gh`` is only needed to obtain the token in the first place, which is
        one process for the life of the client rather than one per request.
        """
        for _attempt in (0, 1):
            token = self._auth_token()
            if not token:
                break
            try:
                return self._rest_http(token, method, path)
            except _TokenExpiredError:
                logger.info("[github_tray] token rejected; minting a fresh one")
                self._forget_token()
        return self._rest_gh(method, path)

    def _graphql(self, query: str) -> dict:
        # GraphQL stays on `gh`: it already holds the session and the host config.
        data = self._run(["api", "graphql", "-f", f"query={query}"])
        if isinstance(data, dict) and data.get("errors") and not data.get("data"):
            error = data["errors"][0]
            message = error.get("message", "GraphQL error")
            raise GitHubClientError(str(message))
        return data.get("data", {}) if isinstance(data, dict) else {}

    # -- menu payload (profile + repositories + followers + workflow runs) --
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
%s
}
"""

    WORKFLOW_FIELDS = """
        databaseId
        name
        displayTitle
        status
        conclusion
        headBranch
        url
        createdAt
        updatedAt
"""

    def _workflow_aliases(self, full_names, limit: int) -> list[tuple[str, str, str]]:
        """``(alias, full_name, field)`` root fields to fold into the menu query.

        One alias per mapped repo turns the N-call REST fan-out into zero extra
        processes; a repo the token cannot see simply comes back null.
        """
        per_page = max(1, int(limit))
        aliases: list[tuple[str, str, str]] = []
        for index, full_name in enumerate(full_names):
            owner, _, name = str(full_name).partition("/")
            if not owner or not name:
                continue
            alias = f"wf{index}"
            aliases.append(
                (
                    alias,
                    str(full_name),
                    f"{alias}:repository(owner: {json.dumps(owner)}, "
                    f"name: {json.dumps(name)})"
                    f"{{ workflowRuns(first: {per_page},"
                    f" orderBy: {{field: CREATED_AT, direction: DESC}})"
                    f"{{ nodes {{{self.WORKFLOW_FIELDS}}} }} }}",
                )
            )
        return aliases

    @staticmethod
    def _shape_run(node: dict, full_name: str) -> dict:
        """REST-compatible keys so one renderer serves both transports."""
        return {
            "id": node.get("databaseId"),
            "name": node.get("name"),
            "display_title": node.get("displayTitle"),
            "status": node.get("status"),
            "conclusion": node.get("conclusion"),
            "head_branch": node.get("headBranch"),
            "html_url": node.get("url"),
            "created_at": node.get("createdAt"),
            "updated_at": node.get("updatedAt"),
            # GraphQL exposes no run_started_at; the created time is the start.
            "run_started_at": node.get("createdAt"),
            "repository_full_name": full_name,
        }

    def fetch_menu(
        self,
        username_fallback: str = "",
        workflow_repos=(),
        workflow_limit: int = 10,
    ) -> dict:
        """Profile, up-to-100 repos, followers and mapped workflow runs in one
        GraphQL call."""
        aliases = self._workflow_aliases(workflow_repos, workflow_limit)
        query = self.MENU_QUERY % "\n".join(entry[2] for entry in aliases)
        data = self._graphql(query)
        viewer = data.get("viewer") or {}
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
        workflows = {}
        for alias, full_name, _field in aliases:
            node = data.get(alias) or {}
            runs = (node.get("workflowRuns") or {}).get("nodes") or []
            if runs:
                workflows[full_name] = [self._shape_run(run, full_name) for run in runs]
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
            "workflows": workflows,
            "web": self.web_base,
        }

    # -- notifications --
    def fetch_notifications(self) -> list[dict]:
        """Unread notifications via the REST endpoint (gh session)."""
        data = self._rest("GET", "notifications?per_page=100")
        return data if isinstance(data, list) else []

    def enrich_notification_states(
        self,
        notifications: list[dict],
        cached: dict | None = None,
        max_age: float = 0.0,
        now: float | None = None,
    ) -> list[dict]:
        """Attach ``_stateInfo`` {state, isDraft}, re-querying only what is stale.

        ``cached`` maps ``owner/repo#number`` to a state entry and is updated
        in place, pruned to the notifications seen so it cannot grow forever.
        """
        store = cached if isinstance(cached, dict) else {}
        if now is None:
            now = time.time()

        keep: dict = {}
        taken: set[str] = set()
        stale: list[tuple] = []
        for notification in notifications:
            subject = notification.get("subject") or {}
            match = _NOTIFICATION_RE.search(str(subject.get("url") or ""))
            if not match or subject.get("type") not in ("Issue", "PullRequest"):
                continue
            owner, repo, kind, number = match.groups()
            key = tray_state.state_info_key(owner, repo, number)
            entry = store.get(key)
            if entry is not None:
                # Retained even when stale, so one failed query is not a full wipe.
                keep[key] = entry
            if tray_state.state_info_is_fresh(
                entry, max_age, now, notification.get("updated_at")
            ):
                notification["_stateInfo"] = tray_state.state_info_payload(entry)
                continue
            stale.append(
                (
                    _alias_for(notification, taken),
                    notification,
                    key,
                    owner,
                    repo,
                    kind,
                    number,
                )
            )

        if stale:
            fields = [self._state_field(entry) for entry in stale]
            try:
                data = self._graphql("{\n" + "\n".join(fields) + "\n}")
            except GitHubClientError as error:
                # Returning bare notifications silently left every pill blank.
                logger.warning(
                    "[github_tray] notification state query failed: %s", error
                )
            else:
                for alias, notification, key, *_rest in stale:
                    node = data.get(alias) or {}
                    item = node.get("pullRequest") or node.get("issue")
                    if not item:
                        continue
                    entry = {
                        "at": now,
                        "state": item.get("state"),
                        "isDraft": bool(item.get("isDraft", False)),
                    }
                    keep[key] = entry
                    notification["_stateInfo"] = tray_state.state_info_payload(entry)

        store.clear()
        store.update(keep)
        return notifications

    @staticmethod
    def _state_field(entry: tuple) -> str:
        """One aliased root field fetching the state of a single issue or PR."""
        alias, _notification, _key, owner, repo, kind, number = entry
        field = "pullRequest" if kind == "pulls" else "issue"
        extras = " isDraft" if field == "pullRequest" else ""
        return (
            f"{alias}:repository(owner: {json.dumps(owner)}, "
            f"name: {json.dumps(repo)})"
            f"{{ {field}(number: {number}) {{ state{extras} }} }}"
        )

    # -- detail payloads: %-placeholders, f-strings would choke on the braces --
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
        data = self._rest("GET", f"repos/{full_name}/actions/runs?per_page={limit}")
        runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
        for run in runs:
            run["repository_full_name"] = full_name
        return runs

    def fetch_avatar_url(self) -> str:
        """Avatar of the authenticated user (REST), '' when unavailable."""
        data = self._rest("GET", "user")
        if isinstance(data, dict):
            return str(data.get("avatar_url") or "")
        return ""

    # -- actions --
    def mark_read(self, thread_id: str) -> None:
        self._rest("PATCH", f"notifications/threads/{thread_id}")

    def rerun_failed_jobs(self, full_name: str, run_id: str) -> None:
        # GitHub accepts an empty POST body for this endpoint.
        self._rest("POST", f"repos/{full_name}/actions/runs/{run_id}/rerun-failed-jobs")

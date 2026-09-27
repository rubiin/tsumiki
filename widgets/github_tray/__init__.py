"""GitHub tray widget package.

Bar button and popover in :mod:`widgets.github_tray.widget`; ``gh`` CLI access
in :mod:`~widgets.github_tray.client`, pure helpers in
:mod:`~widgets.github_tray.state`, reusable GTK bits in
:mod:`~widgets.github_tray.components`.
"""

from .client import GitHubClient, GitHubClientError
from .widget import GitHubTrayPopoverContent, GitHubTrayWidget

__all__ = [
    "GitHubClient",
    "GitHubClientError",
    "GitHubTrayPopoverContent",
    "GitHubTrayWidget",
]

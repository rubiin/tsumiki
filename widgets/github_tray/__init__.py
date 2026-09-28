"""GitHub tray widget package.

Bar button and refresh orchestration in :mod:`widgets.github_tray.widget`,
popover content in :mod:`~widgets.github_tray.popover` (section builders in
``views/``), ``gh``/HTTP access in :mod:`~widgets.github_tray.client`, pure
helpers in :mod:`~widgets.github_tray.state`, reusable GTK bits in
:mod:`~widgets.github_tray.components`.
"""

from .client import GitHubClient, GitHubClientError
from .popover import GitHubTrayPopoverContent
from .widget import GitHubTrayWidget

__all__ = [
    "GitHubClient",
    "GitHubClientError",
    "GitHubTrayPopoverContent",
    "GitHubTrayWidget",
]

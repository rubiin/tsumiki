"""Section renderers for the GitHub tray popover.

Each module is a mixin over :class:`GitHubTrayPopoverContent`: the builders read
``self.tray_widget`` and return GTK children, so they can be split out of the
popover class without changing what they draw.
"""

from .detail import DetailView
from .hero import HeroView
from .inbox import InboxView
from .repos import ReposView
from .status import StatusView

__all__ = ["DetailView", "HeroView", "InboxView", "ReposView", "StatusView"]

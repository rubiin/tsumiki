"""Remember the last value handed to an expensive setter.

Poll handlers re-read state every second and re-apply it unconditionally, but
``set_label``/``set_tooltip_text``/``toggle_css_class`` each invalidate style or
re-render, so an unchanged tick must do neither the read's result nor the write.

Lives in ``utils/`` because both ``services/`` and ``shared/`` already import
from there, and it imports nothing itself, so no cycle is possible.
"""

from collections.abc import Callable
from typing import Any


class ChangeCache:
    """Run a setter only when the value differs from the last one applied."""

    __slots__ = ("_applied",)

    def __init__(self) -> None:
        self._applied: dict[str, Any] = {}

    def apply(self, key: str, value: Any, setter: Callable[[Any], None]) -> bool:
        """Call ``setter(value)`` when *value* changed; return whether it ran.

        The first call for a *key* always runs, so a caller needs no warm-up.
        """
        if key in self._applied and self._applied[key] == value:
            return False
        self._applied[key] = value
        setter(value)
        return True

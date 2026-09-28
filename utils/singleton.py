"""One shared singleton, replacing eight near-identical ``__new__`` caches."""

from __future__ import annotations

from typing import Any

# Keyed by the exact class: a class attribute would be inherited, so a
# subclass would read its parent's "already initialised" flag.
_INSTANCES: dict[type, Any] = {}
_INITIALIZED: set[type] = set()


class SingletonMixin:
    """One instance per class, with an initialisation body that runs once.

    The guard is an explicit ``_init_once()`` rather than a wrapped
    ``__init__``, which stops guarding when a subclass forgets ``super()``.
    """

    # Empty, so a subclass declaring its own ``__slots__`` actually gets one.
    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        # Dropped: object.__new__ rejects them, and they belong to __init__.
        if cls not in _INSTANCES:
            _INSTANCES[cls] = super().__new__(cls)
        return _INSTANCES[cls]

    def _init_once(self) -> bool:
        """Return whether this is the first construction, e.g. guard an ``__init__``."""
        cls = type(self)
        if cls in _INITIALIZED:
            return False
        _INITIALIZED.add(cls)
        return True

    @classmethod
    def reset_instance(cls) -> None:
        """Forget the cached instance. For tests, and for reconfiguration."""
        _INSTANCES.pop(cls, None)
        _INITIALIZED.discard(cls)

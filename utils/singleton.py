"""One shared singleton, replacing eight near-identical ``__new__`` caches."""

from __future__ import annotations

from typing import Any


class SingletonMixin:
    """One instance per class, with an initialisation body that runs once.

    The guard is an explicit ``_init_once()`` rather than a wrapped
    ``__init__``, which stops guarding when a subclass forgets ``super()``.
    """

    _instance: Any = None
    _initialized: bool = False

    def __new__(cls, *args, **kwargs):
        # Dropped: object.__new__ rejects them, and they belong to __init__.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _init_once(self) -> bool:
        """Return whether this is the first construction, e.g. guard an ``__init__``."""
        cls = type(self)
        if cls._initialized:
            return False
        cls._initialized = True
        return True

    @classmethod
    def reset_instance(cls) -> None:
        """Forget the cached instance. For tests, and for reconfiguration."""
        cls._instance = None
        cls._initialized = False

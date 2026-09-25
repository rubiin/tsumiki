"""One shared singleton implementation.

Eight classes each cached their instance in ``__new__`` and guarded ``__init__``
with a slightly different flag. They all wanted the same two things: one
instance per class, and an initialisation body that runs exactly once.
"""

from __future__ import annotations

from typing import Any


class SingletonMixin:
    """One instance per class, with an initialisation body that runs once.

    ``__new__`` does the instance caching, so that part is automatic. The guard
    is explicit - ``_init_once()`` - rather than a wrapped ``__init__``: a
    wrapped one silently stops guarding the first time a subclass forgets to call
    ``super().__init__()``, which is exactly what a shared base must not do.

    Set the flag *before* the body runs, so a re-entrant construction during
    initialisation cannot run it twice.
    """

    _instance: Any = None
    _initialized: bool = False

    def __new__(cls, *args, **kwargs):
        # *args/**kwargs are accepted and dropped: they belong to __init__, and
        # object.__new__ rejects them. Without this, a singleton whose __init__
        # takes arguments cannot be constructed at all.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _init_once(self) -> bool:
        """Return whether this is the first construction.

        Typical use::

            def __init__(self):
                if not self._init_once():
                    return
                ...
        """
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

import atexit
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from typing import Any, TypeVar

from fabric.utils import GLib, logger

# Auto-tune max_workers based on CPU count, fallback to 4
_cpu_count = os.cpu_count() or 4
#: Workers for work that can block for seconds (HTTP, subprocess, D-Bus). Fixed
#: rather than CPU-sized, so a few hung helpers cannot eat the quick pool.
_BLOCKING_WORKERS = 4
thread_pool: ThreadPoolExecutor | None = None
blocking_pool: ThreadPoolExecutor | None = None
_thread_pool_atexit_registered = False
_thread_pool_lock = threading.Lock()

T = TypeVar("T")


def log_errors(func):
    """Log exceptions raised by the wrapped function, then re-raise."""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.exception(f"[decorator] error in {func.__name__}")
            raise

    return wrapper


def safe_operation(func):
    """Catch and log exceptions, returning None instead of propagating."""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"[decorator] {func.__name__} failed: {e}")
            return None

    return wrapper


def _get_thread_pool() -> ThreadPoolExecutor:
    """Lazy-initialize the quick-task thread pool on first use (thread-safe)."""
    global thread_pool, _thread_pool_atexit_registered
    with _thread_pool_lock:
        if thread_pool is None:
            thread_pool = ThreadPoolExecutor(max_workers=_cpu_count)
            if not _thread_pool_atexit_registered:
                atexit.register(_shutdown_thread_pool)
                _thread_pool_atexit_registered = True
    return thread_pool


def _get_blocking_pool() -> ThreadPoolExecutor:
    """Lazy-initialize the blocking-work pool, kept separate from the quick one."""
    global blocking_pool, _thread_pool_atexit_registered
    with _thread_pool_lock:
        if blocking_pool is None:
            blocking_pool = ThreadPoolExecutor(max_workers=_BLOCKING_WORKERS)
            if not _thread_pool_atexit_registered:
                atexit.register(_shutdown_thread_pool)
                _thread_pool_atexit_registered = True
    return blocking_pool


def _shutdown_thread_pool() -> None:
    """Shut both pools down at interpreter exit without blocking joins.

    Ctrl+C can run atexit handlers while another KeyboardInterrupt bubbles.
    """

    global thread_pool, blocking_pool
    with _thread_pool_lock:
        for pool in (thread_pool, blocking_pool):
            if pool is None:
                continue
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except KeyboardInterrupt:
                # Suppress noisy traceback during interpreter teardown.
                pass
            except Exception:
                pass
        thread_pool = None
        blocking_pool = None


def thread(target: Callable[..., T], *args: Any, **kwargs: Any) -> Any:
    """Submit a short task to the quick pool, returning a Future.

    Reserve this for work that finishes in milliseconds (file writes, state
    saves); anything that waits on a network or a subprocess belongs on
    :func:`blocking_thread`.
    """
    return _get_thread_pool().submit(target, *args, **kwargs)


def blocking_thread(target: Callable[..., T], *args: Any, **kwargs: Any) -> Any:
    """Submit a task that may block for a long time, returning a Future."""
    return _get_blocking_pool().submit(target, *args, **kwargs)


def run_worker_with_idle(
    worker: Callable[..., T],
    callback: Callable[[T], Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run *worker* on the pool and hand its result to *callback* via ``idle_add``.

    The idle hop returns to the main thread, so *worker* must not touch widgets.
    """

    def _run() -> T:
        result = worker(*args, **kwargs)
        GLib.idle_add(callback, result)
        return result

    return blocking_thread(_run)


def run_in_thread(func: Callable[..., T]) -> Callable[..., Any]:
    """Decorator running the wrapped function on the blocking pool.

    The decorated methods fetch over the network or shell out, so they must not
    occupy the quick pool's workers.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return blocking_thread(func, *args, **kwargs)

    return wrapper


def replace_timeout(owner, attribute: str, delay_ms: int, callback: Callable[[], bool]):
    """(Re)arm a one-shot timer stored on *owner*, replacing any pending one.

    The callback must clear *attribute* itself to repeat.
    """
    existing = getattr(owner, attribute, None)
    if existing:
        GLib.source_remove(existing)
    setattr(owner, attribute, GLib.timeout_add(delay_ms, callback))
    return getattr(owner, attribute)


def cancel_timeout(owner, attribute: str) -> None:
    """Cancel a timer armed by :func:`replace_timeout`, if one is pending."""
    existing = getattr(owner, attribute, None)
    if existing:
        GLib.source_remove(existing)
        setattr(owner, attribute, None)


def rate_limit(ms: int, skipped_return: Any = None):
    """Rate-limit a method so it runs at most once every ``ms`` milliseconds."""

    interval = ms / 1000.0

    def decorator(func: Callable):
        last_run_attr = f"_rate_limit_last_{func.__name__}"

        def wrapper(self, *args, **kwargs):
            now = monotonic()
            last_run = getattr(self, last_run_attr, 0.0)
            if now - last_run < interval:
                return skipped_return

            setattr(self, last_run_attr, now)
            return func(self, *args, **kwargs)

        return wrapper

    return decorator

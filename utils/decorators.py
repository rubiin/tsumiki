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
thread_pool: ThreadPoolExecutor | None = None
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
    """Lazy-initialize thread pool on first use (thread-safe)."""
    global thread_pool, _thread_pool_atexit_registered
    with _thread_pool_lock:
        if thread_pool is None:
            thread_pool = ThreadPoolExecutor(max_workers=_cpu_count)
            if not _thread_pool_atexit_registered:
                atexit.register(_shutdown_thread_pool)
                _thread_pool_atexit_registered = True
    return thread_pool


def _shutdown_thread_pool() -> None:
    """Best-effort, non-blocking shutdown for interpreter exit.

    On Ctrl+C, Python may run atexit handlers while another KeyboardInterrupt is
    still bubbling; avoid blocking joins to keep shutdown quiet and fast.
    """

    global thread_pool
    with _thread_pool_lock:
        if thread_pool is None:
            return

        try:
            thread_pool.shutdown(wait=False, cancel_futures=True)
        except KeyboardInterrupt:
            # Suppress noisy traceback during interpreter teardown.
            pass
        except Exception:
            pass
        finally:
            thread_pool = None


def thread(target: Callable[..., T], *args: Any, **kwargs: Any) -> Any:
    """
    Submit the given function to the thread pool.
    Returns a Future instead of a Thread.
    """
    return _get_thread_pool().submit(target, *args, **kwargs)


def run_worker_with_idle(
    worker: Callable[..., T],
    callback: Callable[[T], Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run *worker* on the thread pool and deliver its return value to *callback*.

    The result is handed over with ``GLib.idle_add`` because a worker thread
    must not touch widgets. Returns the Future, so a caller that needs to wait
    on the work can still do so.

    Only for workers that just compute a value. A worker that has to report
    failure, or that finishes by scheduling its own completion callback, needs
    to keep its own ``idle_add`` calls.
    """

    def _run() -> T:
        result = worker(*args, **kwargs)
        GLib.idle_add(callback, result)
        return result

    return thread(_run)


def run_in_thread(func: Callable[..., T]) -> Callable[..., Any]:
    """
    Decorator to run the decorated function in the thread pool.
    Returns a Future.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return thread(func, *args, **kwargs)

    return wrapper


def replace_timeout(owner, attribute: str, delay_ms: int, callback: Callable[[], bool]):
    """(Re)arm a one-shot timer stored on *owner*, replacing any pending one.

    The bookkeeping every "remove the old source, then schedule" site repeats.
    The callback is responsible for clearing *attribute* if it needs to know the
    timer has already fired - use it for a repeating poll.
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


def debounce(ms: int):
    """
    Debounce a method. Useful for preventing UI flickering during fast typing.
    Cleans up timers on object deletion.
    """

    def decorator(func: Callable):
        timer_id_attr = f"_debounce_timer_{func.__name__}"

        def wrapper(self, *args, **kwargs):
            # Remove existing timer if present
            existing_timer = getattr(self, timer_id_attr, None)
            if existing_timer:
                GLib.source_remove(existing_timer)

            def timeout_cb():
                setattr(self, timer_id_attr, 0)
                func(self, *args, **kwargs)
                return False

            setattr(self, timer_id_attr, GLib.timeout_add(ms, timeout_cb))

        # Clean up timer on object deletion
        def cleanup(self):
            existing_timer = getattr(self, timer_id_attr, None)
            if existing_timer:
                GLib.source_remove(existing_timer)

        wrapper._debounce_cleanup = cleanup
        return wrapper

    return decorator


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

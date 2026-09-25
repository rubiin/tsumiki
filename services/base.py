import contextlib
from collections.abc import Callable, Sequence

from fabric import Service
from fabric.utils import GLib, exec_shell_command_async, logger


class PollingController:
    """Polls a fixed command on an interval and feeds its output to a callback.

    The next run is armed when the previous process *exits*, not when it
    starts, so a slow command cannot overlap itself. A generation counter drops
    the completion of a run that was stopped or superseded, so pausing cannot
    leave a timer armed.

    *on_start* runs before each command, for callers that reset per-run state.
    """

    def __init__(
        self,
        command: Sequence[str] | str,
        interval_ms: int,
        on_line: Callable[[str], None],
        tag: str = "",
        on_start: Callable[[], None] | None = None,
    ):
        self._command = command
        self._interval_ms = interval_ms
        self._on_line = on_line
        self._tag = tag
        self._on_start = on_start
        self._generation = 0
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Begin polling, with an immediate first run."""
        if self._running:
            return
        self._running = True
        self._poll()

    def stop(self) -> None:
        """Stop polling; a run still in flight is ignored when it finishes."""
        self._running = False
        self._generation += 1

    def _poll(self) -> None:
        if not self._running:
            return

        if self._on_start is not None:
            self._on_start()
        self._generation += 1
        generation = self._generation
        try:
            process, _stdout = exec_shell_command_async(self._command, self._on_line)
        except GLib.Error as e:
            logger.warning(f"[{self._tag}] poll could not start: {e.message}")
            self._arm(generation)
            return

        process.wait_async(
            None,
            lambda proc, result, generation=generation: self._on_exited(
                proc, result, generation
            ),
        )

    def _on_exited(self, process, result, generation: int) -> None:
        with contextlib.suppress(GLib.Error):
            process.wait_finish(result)
        self._arm(generation)

    def _arm(self, generation: int) -> None:
        """Schedule the next run, unless this one was stopped or superseded."""
        if not self._running or generation != self._generation:
            return
        GLib.timeout_add(self._interval_ms, self._tick)

    def _tick(self) -> bool:
        self._poll()
        return False


class SingletonService(Service):
    """Base service class with singleton pattern and common functionality."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, **kwargs):
        if hasattr(self, "_initialized"):
            return
        super().__init__(**kwargs)
        self._initialized = True

import contextlib
import shlex
import time
from collections.abc import Callable, Sequence
from typing import Any

from fabric import Service
from fabric.utils import Gio, GLib, exec_shell_command_async, logger

from utils.functions import find_executable
from utils.singleton import SingletonMixin

# Returned by ``parse_line`` for a line that carries no state at all.
IGNORED = object()

# Module-level so a test can measure a poll cycle without sleeping.
_monotonic = time.monotonic


class SingletonService(SingletonMixin, Service):
    """Base service class with singleton pattern and common functionality."""


def _drain_stderr(process, tag: str) -> None:
    """Read the child's stderr to EOF, one line at a time.

    Fabric always opens ``STDERR_PIPE`` but only streams stdout, so nothing
    reads it: a command writing more than the pipe buffer (~64 KB) blocks in
    ``write`` and never exits, which kills the poll chain without a log line.
    """
    stream = Gio.DataInputStream(
        base_stream=process.get_stderr_pipe(),
        close_base_stream=True,
    )

    def read(_stream, res) -> None:
        try:
            line, *_ = stream.read_line_finish_utf8(res)
        except GLib.Error as e:
            logger.debug(f"[{tag}] stderr read failed: {e.message}")
            return
        if line is None:
            return  # EOF
        logger.debug(f"[{tag}] {line.strip()}")
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, read)

    stream.read_line_async(GLib.PRIORITY_DEFAULT, None, read)


class PollingController:
    """Polls a fixed command on an interval and feeds its output to a callback.

    The next run is armed when the previous process *exits*, so a slow command
    cannot overlap itself; a generation counter drops late completions.
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
        # The armed timer must be cancellable, not just disarmed by a flag.
        self._source_id = 0
        self._started_at = 0.0
        self._in_flight = False
        self._pending = False

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
        """Stop polling, cancelling the armed timer; a run in flight is ignored."""
        self._running = False
        self._generation += 1
        self._pending = False
        self._disarm()

    def poll_now(self) -> None:
        """Run the command now, deferring by one cycle if a run is in flight.

        Used to react to an event signal instead of waiting out the interval.
        """
        if not self._running:
            return
        if self._in_flight:
            self._pending = True
            return
        self._poll()

    def _disarm(self) -> None:
        """Cancel the armed source, so a stopped poller leaves no timer behind."""
        if self._source_id:
            GLib.source_remove(self._source_id)
            self._source_id = 0

    def _poll(self) -> None:
        if not self._running:
            return

        if self._on_start is not None:
            self._on_start()
        self._generation += 1
        generation = self._generation
        self._started_at = _monotonic()
        self._in_flight = True
        try:
            process, _stdout = exec_shell_command_async(self._command, self._on_line)
        except GLib.Error as e:
            self._in_flight = False
            logger.warning(f"[{self._tag}] poll could not start: {e.message}")
            self._arm(generation)
            return

        _drain_stderr(process, self._tag)
        process.wait_async(
            None,
            lambda proc, result, generation=generation: self._on_exited(
                proc, result, generation
            ),
        )

    def _on_exited(self, process, result, generation: int) -> None:
        self._in_flight = False
        with contextlib.suppress(GLib.Error):
            process.wait_finish(result)
        self._warn_if_overrunning(generation)
        if self._pending and generation == self._generation:
            # A signal asked for a fresher read than the one that just landed.
            self._pending = False
            self._poll()
            return
        self._arm(generation)

    def _warn_if_overrunning(self, generation: int) -> None:
        """Report a cycle far longer than the interval: the command is wedged."""
        if generation != self._generation:
            return
        elapsed = _monotonic() - self._started_at
        if elapsed > 2 * self._interval_ms / 1000:
            logger.warning(
                f"[{self._tag}] poll cycle took {elapsed:.1f}s, "
                f"over twice its {self._interval_ms / 1000:.0f}s interval"
            )

    def _arm(self, generation: int) -> None:
        """Schedule the next run, unless this one was stopped or superseded."""
        if not self._running or generation != self._generation:
            return
        self._source_id = GLib.timeout_add(self._interval_ms, self._tick)

    def _tick(self) -> bool:
        # The source has fired, so its id is stale: clearing it keeps stop()
        # from removing a source that is already gone.
        self._source_id = 0
        self._poll()
        return False


class PolledCommandService(SingletonService):
    """A service whose state comes from polling one command's stdout.

    The base owns the poller, the state field and the transition check, so a
    poll that reads the same value again stays silent instead of waking every
    listener once per interval. Subclasses pass the *name* of a method that
    takes one stdout line and returns the state it implies, or ``IGNORED``.
    """

    def __init__(
        self,
        command: Sequence[str] | str,
        interval_ms: int,
        parse_line: str,
        tag: str,
        state: Any = None,
        on_start: Callable[[], None] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._tag = tag
        self._state = state
        self._binary = self._first_word(command)
        self._parse = getattr(self, parse_line)
        self._poller = PollingController(
            command,
            interval_ms,
            self._on_line,
            tag=tag,
            on_start=on_start,
        )
        self.start_polling()

    @staticmethod
    def _first_word(command: Sequence[str] | str) -> str:
        """The binary a command runs, which is what decides whether to poll."""
        if isinstance(command, str):
            return shlex.split(command)[0]
        return command[0]

    # ── Polling ─────────────────────────────────────────────────

    def start_polling(self) -> None:
        """Poll only when the command's binary is installed.

        A missing binary would otherwise cost one failed spawn per interval,
        forever, to feed a widget that can only ever show its fallback.
        """
        if not find_executable(self._binary):
            logger.info(f"[{self._tag}] {self._binary} is not installed; not polling")
            return
        self._poller.start()

    def pause_polling(self) -> None:
        """Stop polling — call when the widget is destroyed."""
        self._poller.stop()

    def resume_polling(self) -> None:
        """Restart polling, re-checking the binary so a late install is noticed."""
        self.start_polling()

    # ── State ───────────────────────────────────────────────────

    def _on_line(self, line: str) -> None:
        new_state = self._parse(line)
        if new_state is not IGNORED:
            self._set_state(new_state)

    def _set_state(self, value: Any) -> bool:
        """Store *value*, publishing it only when it actually differs."""
        if value == self._state:
            return False
        self._state = value
        self._on_state_changed(value)
        self.emit("changed")
        return True

    def _on_state_changed(self, value: Any) -> None:
        """Hook for subclasses that keep derived state beside the value."""

    # ── Teardown ────────────────────────────────────────────────

    def destroy(self) -> None:
        """Stop the poller; fabric's ``Service`` has no ``destroy`` to chain to."""
        self._poller.stop()

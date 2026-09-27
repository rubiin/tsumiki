"""Launcher slash command: /calc — evaluate math expressions via libqalculate."""

import os
import re
import threading
from typing import ClassVar

from utils.functions import find_executable
from utils.plugin_manager import (
    LauncherPlugin,
    PluginResult,
    SubprocessTimeoutError,
    copy_to_clipboard,
    run_subprocess,
)

_QALC_EXE = "qalc"
_EVAL_TIMEOUT_SECONDS = 10
# qalc prints a Unicode minus sign (U+2212) — normalize it for copy/paste.
_UNICODE_MINUS = "\u2212"
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
# Concurrent invocations contend on qalc's config/lock file.
_QALC_LOCK = threading.Lock()


def find_qalc() -> str | None:
    """Return the qalc binary path, or None if libqalculate is not installed."""
    return find_executable(_QALC_EXE)


def evaluate(expr: str, qalc_path: str | None = None, runner=None) -> str:
    """Evaluate *expr* with qalc; raises ValueError on failure/timeout."""
    qalc = qalc_path or find_qalc()
    if qalc is None:
        raise ValueError("qalc not found — install libqalculate")
    run = runner or run_subprocess

    try:
        with _QALC_LOCK:
            result = run(
                [qalc, "-t", "--", expr],
                capture_output=True,
                text=True,
                timeout=_EVAL_TIMEOUT_SECONDS,
                # Deterministic decimal separator while keeping UTF-8 output.
                env={**os.environ, "LC_ALL": "C.UTF-8"},
            )
    except SubprocessTimeoutError as exc:
        raise ValueError("calculation timed out") from exc

    output = _ANSI_ESCAPE_RE.sub("", result.stdout).strip()
    error = result.stderr.strip()
    if result.returncode != 0 or not output:
        raise ValueError(error or f"qalc failed (exit {result.returncode})")

    return output.replace(_UNICODE_MINUS, "-")


class CalcPlugin(LauncherPlugin):
    """Slash command: /calc — evaluate math/units/currency via libqalculate."""

    name = "calc"
    description = "Evaluate math, units and currency (libqalculate)"
    icon = "accessories-calculator-symbolic"
    aliases: ClassVar[list[str]] = ["calculator", "math"]
    # Each query forks qalc; debounce instead of re-evaluating per keystroke.
    debounce_ms = 400

    def __init__(self):
        super().__init__()
        self._qalc = find_qalc()

    def handle(self, args: str) -> list[PluginResult]:
        expr = args.strip()
        if not expr:
            return [
                PluginResult(
                    "Usage: /calc <expression>",
                    subtitle="e.g. /calc 100 cm to inches  or  /calc sqrt(2)",
                    icon=self.icon,
                )
            ]
        if self._qalc is None:
            return [
                PluginResult(
                    "/calc requires libqalculate",
                    subtitle="Install qalc, e.g. sudo pacman -S libqalculate",
                    icon="dialog-error-symbolic",
                )
            ]
        if self.is_cancelled():
            return []  # superseded before we even started
        try:
            result = evaluate(expr, self._qalc, runner=self.run_subprocess)
        except Exception as exc:
            return [
                PluginResult(
                    "Invalid expression",
                    subtitle=f"{exc}",
                    icon="dialog-error-symbolic",
                )
            ]
        return [
            PluginResult(
                f"{expr} = {result}",
                subtitle="Press Enter to copy the result",
                icon=self.icon,
                data=result,
            )
        ]

    def execute(self, result: PluginResult | None = None) -> bool:
        if result is not None and result.data:
            copy_to_clipboard(str(result.data))
        return False  # close the launcher after copying

import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime

from fabric.core.service import Property, Signal
from fabric.utils import (
    Gio,
    GLib,
    exec_shell_command,
    exec_shell_command_async,
    idle_add,
    logger,
    os,
)

import utils.functions as helpers
from utils.constants import APPLICATION_NAME, ASSETS_DIR
from utils.decorators import thread
from utils.icons import symbolic_icons

from .base import SingletonService


class ScreenRecorderService(SingletonService):
    """Service to handle screen recording"""

    @Signal
    def recording(self, value: bool) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.home_dir = GLib.get_home_dir()
        self.shutter_sound = f"{ASSETS_DIR}/sounds/camera-shutter.mp3"
        self._start_recording_timer_id = None
        self._screenshot_timer_id = None

    def record_and_emit(self, command):
        self._start_recording_timer_id = None
        exec_shell_command_async(command, lambda *_: None)
        self.emit("recording", True)
        return False  # Only run once

    def screenrecord_start(
        self,
        config: dict,
        fullscreen=False,
    ):
        path = config.get("path", "")
        """Start screen recording using wf-recorder with optional GLib-based delay."""
        if not path:
            logger.exception("[SCREENRECORD] No path provided for screen recording.")
            return

        self.screenrecord_path = os.path.join(self.home_dir, path)

        if self.is_recording:
            logger.exception(
                "[SCREENRECORD] Another instance of wf-recorder is already running."
            )
            return

        timestamp = datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = os.path.join(self.screenrecord_path, f"{timestamp}.mp4")
        self._current_screencast_path = file_path

        audio = "--audio" if config.get("audio", False) else ""
        delayed = config.get("delayed", False)
        timeout = config.get("delayed_timeout", 5000)

        if fullscreen:
            self._start_recording(audio, "", file_path, delayed, timeout)
            return

        # slurp blocks — run it off the UI thread and marshal back via idle_add.
        def _slurp_worker():
            geometry = exec_shell_command("slurp")
            idle_add(self._on_slurp, geometry, audio, file_path, delayed, timeout)

        thread(_slurp_worker)

    def _on_slurp(self, geometry, audio, file_path, delayed, timeout):
        area = f"-g '{geometry}'" if geometry else ""
        self._start_recording(audio, area, file_path, delayed, timeout)

    def _start_recording(self, audio, area, file_path, delayed, timeout):
        command = (
            f"wf-recorder {audio} --file={file_path} --pixel-format yuv420p {area}"
        )
        if delayed:
            if self._start_recording_timer_id is not None:
                GLib.source_remove(self._start_recording_timer_id)
            self._start_recording_timer_id = GLib.timeout_add(
                timeout, self.record_and_emit, command
            )
        else:
            self.record_and_emit(command)

    def _open_in_file_manager(self, directory: str) -> None:
        """Open a directory in the user's file manager.

        A list, not a shell string: the paths are user-configured and must not
        be re-parsed by a shell.
        """
        exec_shell_command_async(["xdg-open", directory])

    def _open_path(self, path: str, *command: str) -> None:
        """Run ``command path`` without a shell - e.g. ``swappy -f <file>``."""
        exec_shell_command_async([*command, path])

    def _send_file_notification(
        self,
        *,
        log_tag: str,
        summary: str,
        body: str,
        icon: str,
        utility: str,
        icon_hint: str,
        actions: Sequence[tuple[str, str, Callable[[], None]]],
    ) -> None:
        """Show a notification whose buttons run *actions*.

        ``notify-send`` prints the chosen action's key on stdout when one is
        invoked, so each entry is ``(key, label, handler)`` and the key is what
        comes back to dispatch on.
        """
        cmd = ["notify-send"]
        for key, label, _handler in actions:
            cmd.extend(["-A", f"{key}={label}"])
        cmd.extend(
            [
                "-t",
                "5000",
                "-i",
                icon,
                "-a",
                f"{APPLICATION_NAME} {utility}",
                "-h",
                icon_hint,
                summary,
                body,
            ]
        )

        proc: Gio.Subprocess = Gio.Subprocess.new(cmd, Gio.SubprocessFlags.STDOUT_PIPE)
        handlers = {key: handler for key, _label, handler in actions}

        def _callback(process: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, _stderr = process.communicate_utf8_finish(task)
            except GLib.Error as err:
                logger.exception(f"[{log_tag}] Failed read notification action: {err}")
                return

            if (handler := handlers.get(stdout.strip("\n"))) is not None:
                handler()

        proc.communicate_utf8_async(None, None, _callback)

    def send_screenshot_notification(self, file_path=None):
        if not file_path:
            # Clipboard capture: there is no file to point at, so no actions,
            # icon hint or timeout override.
            proc = Gio.Subprocess.new(
                ["notify-send", "Screenshot Sent to Clipboard"],
                Gio.SubprocessFlags.STDOUT_PIPE,
            )
            proc.communicate_utf8_async(None, None, None)
            return

        self._send_file_notification(
            log_tag="SCREENSHOT",
            summary="Screenshot Saved",
            body=f"Saved Screenshot at {file_path}",
            icon=symbolic_icons["ui"]["camera"],
            utility="Screenshot Utility",
            icon_hint=f"STRING:image-path:{file_path}",
            actions=(
                (
                    "files",
                    "Show in Files",
                    lambda: self._open_in_file_manager(self.screenshot_path),
                ),
                ("view", "View", lambda: self._open_path(file_path, "xdg-open")),
                (
                    "edit",
                    "Edit",
                    lambda: self._open_path(file_path, "swappy", "-f"),
                ),
            ),
        )

    def screenshot(
        self,
        config: dict,
        fullscreen=False,
        save_copy=True,
    ):
        path = config.get("path", "")
        """Take a screenshot using grimblast and optionally annotate with satty."""
        if not path:
            logger.exception("[SCREENSHOT] No path provided for screenshot.")
            return

        self.screenshot_path = os.path.join(self.home_dir, path)
        timestamp = datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = os.path.join(self.screenshot_path, f"{timestamp}.png")

        annotate = config.get("annotation", False)

        temp_path = file_path  # Default to final path if no annotation

        # Determine the target screenshot file
        if annotate:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_path = temp_file.name

        # Prepare grimblast command
        command = (
            ["grimblast", "copysave", "screen", temp_path]
            if save_copy
            else ["grimblast", "copyscreen"]
        )

        if not fullscreen and len(command) > 2:
            command[2] = "area"

        def _annotate_and_notify():
            """Run satty off the main thread, then marshal back."""
            try:
                if helpers.run_command(
                    ["satty", "--filename", temp_path, "--output-filename", file_path]
                ) is None:
                    logger.warning("[SCREENSHOT] satty annotation failed")
                    return
                os.unlink(temp_path)
            except OSError as e:
                logger.exception(f"[SCREENSHOT] Error in annotation: {e}")
                return

            def _notify():
                if config.get("capture_sound", False):
                    helpers.play_sound(self.shutter_sound)
                self.send_screenshot_notification(file_path=file_path)
                return False

            idle_add(_notify)

        def after_screenshot(*_):
            try:
                if annotate:
                    # Run satty off the main thread to avoid blocking the
                    # GTK event loop while the annotation window is open.
                    thread(_annotate_and_notify)
                    return

                if config.get("capture_sound", False):
                    helpers.play_sound(self.shutter_sound)

                # Send notification after annotation or direct capture
                self.send_screenshot_notification(file_path=file_path)

            except OSError as e:
                logger.exception(
                    f"[SCREENSHOT] Error in annotation or notification: {e}"
                )

        def take_screenshot():
            self._screenshot_timer_id = None
            try:
                exec_shell_command_async(" ".join(command), after_screenshot)
            except (GLib.Error, OSError):
                logger.exception(f"[SCREENSHOT] Failed to run command: {command}")
            return False

        if config.get("delayed", False):
            timeout = config.get("delayed_timeout", 5000)
            if self._screenshot_timer_id is not None:
                GLib.source_remove(self._screenshot_timer_id)
            self._screenshot_timer_id = GLib.timeout_add(timeout, take_screenshot)
        else:
            take_screenshot()

    def send_screenrecord_notification(self, file_path: str):
        self._send_file_notification(
            log_tag="SCREENRECORD",
            summary="Screenrecord Saved",
            body=f"Saved Screencast at {file_path}",
            icon=symbolic_icons["ui"]["camera-video"],
            utility="Recording Utility",
            icon_hint=f"STRING:image-path:{file_path}",
            actions=(
                (
                    "files",
                    "Show in Files",
                    lambda: self._open_in_file_manager(self.screenrecord_path),
                ),
                ("view", "View", lambda: self._open_path(file_path, "xdg-open")),
            ),
        )

    @Property(bool, "readable", default_value=False)
    def is_recording(self):
        return helpers.is_app_running("wf-recorder")

    def screenrecord_stop(self):
        helpers.kill_process("wf-recorder")
        self.emit("recording", False)
        self.send_screenrecord_notification(self._current_screencast_path)

import contextlib
import json
import signal

from fabric.utils import (
    Gdk,
    Gio,
    GLib,
    bulk_connect,
    exec_shell_command_async,
    idle_add,
    invoke_repeater,
    logger,
    os,
    remove_handler,
)
from fabric.widgets.label import Label

from shared.widget_container import ButtonWidget
from utils.colors import Colors
from utils.widget_utils import nerd_font_icon

# Module-level constants - evaluated once at import
_BUTTON_HANDLERS = {
    1: "on_click",
    2: "on_click_middle",
    3: "on_click_right",
}

_SCROLL_HANDLERS = {
    Gdk.ScrollDirection.UP: "on_scroll_up",
    Gdk.ScrollDirection.DOWN: "on_scroll_down",
}


def _get_config_value(module_config: dict, *keys: str, default=None):
    for key in keys:
        if key in module_config:
            return module_config[key]
    return default


class CustomWidgetPresenter:
    """Formats and applies command output to widget UI."""

    def __init__(self, module_config: dict, text_label: Label, icon, host_widget):
        self._config = module_config
        self._text_label = text_label
        self._icon = icon
        self._host_widget = host_widget
        # ``format`` is Waybar's key; accept it so Waybar configs work verbatim.
        self._format_str = _get_config_value(
            module_config, "label_format", "format", default="{}"
        )
        self._max_len = _get_config_value(
            module_config,
            "max_length",
            "max-length",
            default=0,
        )
        self._min_len = _get_config_value(
            module_config,
            "min_length",
            "min-length",
            default=0,
        )
        self._tooltip_enabled = _get_config_value(
            module_config, "tooltip", default=True
        )
        self._tooltip_format = _get_config_value(
            module_config,
            "tooltip_format",
            "tooltip-format",
            default=None,
        )
        self._last_class: str | None = None

    def handle_output(self, output: str):
        if not output:
            return

        stripped = output.strip()
        return_type = self._config.get("return_type", "plain")
        if return_type == "json" or stripped.startswith("{"):
            self._handle_json_output(stripped)
            return
        self._handle_text_output(stripped)

    def _format_text(self, text: str) -> str:
        display_text = (
            self._format_str.replace("{}", str(text))
            if "{}" in self._format_str
            else text
        )
        if self._min_len > 0 and len(display_text) < self._min_len:
            display_text = display_text.ljust(self._min_len)
        if self._max_len > 0 and len(display_text) > self._max_len:
            display_text = display_text[: self._max_len] + "…"
        return display_text

    def _format_tooltip(self, tooltip_text: str) -> str:
        if self._tooltip_format and "{}" in self._tooltip_format:
            return self._tooltip_format.replace("{}", tooltip_text)
        return tooltip_text

    def _update_icon(self, alt: str | None, percentage: int | None):
        if not self._icon:
            return

        format_icons = self._config.get("format_icons", {})
        if not format_icons:
            return

        icon = None
        if alt and alt in format_icons:
            icon = format_icons[alt]
        elif percentage is not None:
            # Dict order is the user's, so thresholds must be walked high to low
            # or 80% would match a "50" entry that happens to come first.
            thresholds = sorted(
                (int(k) for k in format_icons if isinstance(k, str) and k.isdigit()),
                reverse=True,
            )
            for threshold in thresholds:
                if percentage >= threshold:
                    icon = format_icons[str(threshold)]
                    break

        if icon:
            self._icon.set_label(icon)

    def _handle_json_output(self, output: str):
        try:
            data = json.loads(output)
            if not isinstance(data, dict):
                self._handle_text_output(str(data))
                return
            text = data.get("text", "")
            alt = data.get("alt", "")
            percentage = data.get("percentage")
            self._text_label.set_label(self._format_text(text))

            if self._tooltip_enabled:
                tooltip = data.get("tooltip", "")
                if tooltip:
                    # Plain text: command output can hold '&' or '<' that is not
                    # valid Pango, which silently renders an empty tooltip.
                    self._host_widget.set_tooltip_text(
                        self._format_tooltip(str(tooltip))
                    )
                else:
                    self._host_widget.set_tooltip_text("")

            new_class = data.get("class")
            if new_class != self._last_class:
                if self._last_class:
                    self._host_widget.remove_style_class(self._last_class)
                if new_class:
                    self._host_widget.add_style_class(new_class)
                self._last_class = new_class

            self._update_icon(alt, percentage)

        except json.JSONDecodeError as err:
            logger.warning(f"{Colors.WARNING}[CustomWidget] Invalid JSON output: {err}")
            self._handle_text_output(output)

    def _handle_text_output(self, output: str):
        formatted = self._format_text(output)
        self._text_label.set_label(formatted)
        if self._tooltip_enabled:
            self._host_widget.set_tooltip_text(self._format_tooltip(str(output)))


class CustomWidgetExecutor:
    """Owns command lifecycle, timers, process streaming, and signal cleanup."""

    def __init__(self, module_config: dict, on_output):
        self._config = module_config
        self._on_output = on_output
        self._exec_cmd = module_config.get("exec")
        self._interval = module_config.get("interval", 0)
        self._process: Gio.Subprocess | None = None
        self._repeater_handler_id: int | None = None
        self._restart_timer_id: int | None = None
        self._actual_signal: int | None = None
        self._original_signal_handler = None

    def register_signal(self, sig_num: int):
        actual_signal = signal.SIGRTMIN + sig_num
        self._original_signal_handler = signal.getsignal(actual_signal)

        def on_signal(*_):
            self.execute_once()

        signal.signal(actual_signal, on_signal)
        self._actual_signal = actual_signal

    def start(self):
        if not self._exec_cmd:
            logger.warning(
                f"{Colors.WARNING}[CustomWidget] No 'exec' command specified"
            )
            return

        if self._interval > 0:
            self.execute_once()
            self._repeater_handler_id = invoke_repeater(
                self._interval,
                self._periodic_execute,
            )
            return

        if self._config.get("restart_interval", 0) > 0:
            self._start_continuous()
            return

        self.execute_once()

    def execute_once(self):
        if not self._exec_cmd:
            return
        exec_shell_command_async(
            os.path.expanduser(self._exec_cmd),
            self._on_output,
        )

    def _periodic_execute(self, *_) -> bool:
        self.execute_once()
        return True

    def _start_continuous(self):
        if not self._exec_cmd:
            return
        if self._process and self._process.get_if_running():
            return

        restart = self._config.get("restart_interval", 0)

        try:
            process, _ = exec_shell_command_async(
                os.path.expanduser(self._exec_cmd),
                lambda line: idle_add(self._on_output, line.strip()),
            )
            self._process = process

            if process and restart > 0:

                def _on_exit(proc, task):
                    with contextlib.suppress(Exception):
                        proc.wait_finish(task)
                    if getattr(self, "_destroyed", False):
                        return
                    self._restart_timer_id = GLib.timeout_add(
                        restart * 1000, self._start_continuous
                    )

                process.wait_async(GLib.PRIORITY_DEFAULT, None, _on_exit)
        except Exception as err:
            logger.exception(
                f"{Colors.ERROR}[CustomWidget] "
                f"Failed to start continuous command: {err}"
            )

    def cleanup(self):
        self._destroyed = True

        if self._repeater_handler_id:
            remove_handler(self._repeater_handler_id)
            self._repeater_handler_id = None

        if self._restart_timer_id is not None:
            GLib.source_remove(self._restart_timer_id)
            self._restart_timer_id = None

        if (
            self._actual_signal is not None
            and self._original_signal_handler is not None
        ):
            signal.signal(self._actual_signal, self._original_signal_handler)
            self._actual_signal = None
            self._original_signal_handler = None

        if not self._process:
            return
        self._process.force_exit()
        self._process = None


class CustomWidget(ButtonWidget):
    """A Waybar-compatible custom widget."""

    __slots__ = (
        "_exec_on_event",
        "_executor",
        "_presenter",
        "_signal_handler_id",
        "icon",
        "module_config",
        "text_label",
    )

    def __init__(
        self,
        widget_name: str = "custom_widget",
        config: dict | None = None,
        **kwargs,
    ):
        super().__init__(name=widget_name, **kwargs)

        # Use passed config or get from widget_config
        self.module_config = config or self.config
        self._signal_handler_id: int | None = None

        # Cache frequently accessed config values
        self._exec_on_event = _get_config_value(
            self.module_config,
            "exec_on_event",
            "exec-on-event",
            default=False,
        )

        icon = self.module_config.get("format_icons", {}).get("default")
        if icon:
            self.icon = nerd_font_icon(
                icon=icon,
                props={"style_classes": ["panel-font-icon"]},
            )
            self.container_box.add(self.icon)
        else:
            self.icon = None

        self.text_label = Label(label="", style_classes="panel-text")
        self.container_box.add(self.text_label)

        rotation = self.module_config.get("rotate", 0)
        if rotation:
            self.text_label.set_angle(rotation)

        self.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)

        bulk_connect(
            self,
            {
                "button-press-event": self._on_button_press,
                "scroll-event": self._on_scroll,
            },
        )

        self._presenter = CustomWidgetPresenter(
            self.module_config,
            self.text_label,
            self.icon,
            self,
        )
        self._executor = CustomWidgetExecutor(
            self.module_config,
            self._presenter.handle_output,
        )

        # Register signal handler for external updates (like waybar's signal feature)
        sig = self.module_config.get("signal")
        if sig and isinstance(sig, int):
            try:
                self._register_signal(sig)
            except Exception as e:
                logger.exception(
                    f"{Colors.WARNING}[CustomWidget] Failed to register signal: {e}"
                )

        self._start_execution()

        # GTK destroys children from C, so cleanup hangs off the signal.
        self.connect("destroy", self._on_destroy)

    def _register_signal(self, sig_num: int):
        """Register a Unix signal handler to trigger updates."""
        self._executor.register_signal(sig_num)
        self._signal_handler_id = sig_num

    def _start_execution(self):
        """Start command execution via executor."""
        self._executor.start()

    def _execute_command(self):
        """Execute the configured command asynchronously."""
        self._executor.execute_once()

    def _handle_output(self, output: str):
        """Handle command output (plain text or JSON)."""
        self._presenter.handle_output(output)

    def _format_text(self, text: str) -> str:
        """Apply format string and max_length to text."""
        return self._presenter._format_text(text)

    def _update_icon(self, alt: str | None, percentage: int | None):
        """Update icon based on alt or percentage."""
        self._presenter._update_icon(alt, percentage)

    def _handle_json_output(self, output: str):
        """Parse Waybar-compatible JSON output."""
        self._presenter._handle_json_output(output)

    def _handle_text_output(self, output: str):
        """Handle plain text output."""
        self._presenter._handle_text_output(output)

    def _on_button_press(self, widget, event) -> bool:
        """Handle button press events."""
        handler_key = _BUTTON_HANDLERS.get(event.button)
        if not handler_key:
            return False

        cmd = _get_config_value(
            self.module_config,
            handler_key,
            handler_key.replace("_", "-"),
            default=None,
        )
        if not cmd:
            return False

        exec_shell_command_async(os.path.expanduser(cmd), lambda _: None)

        # Re-execute main command if exec_on_event is true
        if self._exec_on_event:
            self._execute_command()

        return True

    def _on_scroll(self, widget, event) -> bool:
        """Handle scroll events (both discrete and smooth scrolling)."""
        direction = event.direction

        # Handle smooth scrolling (touchpads and modern mice)
        if direction == Gdk.ScrollDirection.SMOOTH:
            _, _, delta_y = event.get_scroll_deltas()
            if delta_y > 0:
                handler_key = "on_scroll_down"
            elif delta_y < 0:
                handler_key = "on_scroll_up"
            else:
                return False
        else:
            # Handle discrete scrolling (traditional scroll wheels)
            handler_key = _SCROLL_HANDLERS.get(direction)
            if not handler_key:
                return False

        cmd = _get_config_value(
            self.module_config,
            handler_key,
            handler_key.replace("_", "-"),
            default=None,
        )
        if not cmd:
            return False

        exec_shell_command_async(os.path.expanduser(cmd), lambda _: None)

        if self._exec_on_event:
            self._execute_command()

        return True

    def _on_destroy(self, *_):
        """Stop the command timers and kill the subprocess; runs for C destroys."""
        self._executor.cleanup()

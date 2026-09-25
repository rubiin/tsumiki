import math

from fabric.utils import GLib, Gtk
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay

from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget, TeardownMixin
from utils.i18n import _


class CircularProgressWidget(Gtk.DrawingArea):
    """Circular progress ring for pomodoro timer."""

    def __init__(self, size=160):
        super().__init__(visible=True)
        self.size = size
        self.progress = 0.0
        self.set_size_request(size, size)
        self.connect("draw", self.on_draw)

    def set_progress(self, progress: float):
        self.progress = min(1.0, max(0.0, progress))
        self.queue_draw()

    def on_draw(self, area, cr):
        alloc = self.get_allocation()
        cx = alloc.width / 2
        cy = alloc.height / 2
        radius = min(alloc.width, alloc.height) / 2 - 10

        # Background ring
        cr.set_source_rgba(1, 1, 1, 0.15)
        cr.set_line_width(8)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        # Progress ring
        start_angle = -math.pi / 2
        end_angle = start_angle + (2 * math.pi * self.progress)
        cr.set_source_rgba(1, 0.85, 0.85, 1)  # pastel pink
        cr.set_line_width(8)
        cr.arc(cx, cy, radius, start_angle, end_angle)
        cr.stroke()


class PomodoroMenu(Box, TeardownMixin):
    """Popover content for pomodoro timer."""

    def __init__(self, parent=None, **kwargs):
        super().__init__(
            name="pomodoro-menu",
            orientation="v",
            spacing=16,
            **kwargs,
        )

        self._parent = parent

        # Timer state
        self.work_duration = 25 * 60  # 25 min
        self.short_break = 5 * 60  # 5 min
        self.long_break = 15 * 60  # 15 min
        self.sessions_until_long_break = 4

        self.elapsed = 0
        self.is_running = False
        self.is_work_session = True
        self.session_count = 1
        self.completed_sessions = 0
        self.timer_id = None

        # Session counter
        self.session_label = Label(
            name="pomodoro-session",
            markup="<span font='11' color='#cccccc'>Session 1/8</span>",
            h_align="center",
        )

        # Phase indicator
        self.phase_label = Label(
            name="pomodoro-phase",
            markup="<span font='12' color='#ffffff'>Work</span>",
            h_align="center",
        )

        # Circular progress
        self.progress = CircularProgressWidget(size=200)

        self._icon_play = ""
        self._icon_pause = ""
        self._icon_skip = ""
        self._icon_refresh = ""

        # Timer display (MM:SS format)
        self.timer_label = Label(
            name="pomodoro-timer",
            markup="<span font='38' color='#f0d0d0'>00:00</span>",
            h_align="center",
            v_align="center",
        )

        center_content = Box(
            name="pomodoro-overlay-content",
            orientation="v",
            spacing=6,
            h_align="center",
            v_align="center",
            children=[
                self.phase_label,
                self.timer_label,
            ],
        )

        progress_overlay = Overlay(
            name="pomodoro-progress-overlay",
            child=self.progress,
            overlays=[center_content],
        )

        center_box = Box(
            name="pomodoro-center",
            orientation="v",
            spacing=12,
            h_align="center",
            children=[
                progress_overlay,
            ],
        )

        # Control buttons
        self.btn_pause = Button(
            label=f"{self._icon_play} Start",
            on_clicked=self._on_pause_click,
            name="pomodoro-btn-pause",
        )
        self.btn_skip = Button(
            label=f"{self._icon_skip} Skip",
            on_clicked=self._on_skip_click,
            name="pomodoro-btn-skip",
        )
        self.btn_reset = Button(
            label=f"{self._icon_refresh} Reset",
            on_clicked=self._on_reset_click,
            name="pomodoro-btn-reset",
        )
        self.btn_reset_all = Button(
            label=f"{self._icon_refresh} Reset All",
            on_clicked=self._on_reset_all_click,
            name="pomodoro-btn-reset-all",
        )

        buttons_top = Box(
            name="pomodoro-buttons-top",
            spacing=8,
            h_align="center",
            children=[self.btn_pause, self.btn_skip],
        )
        buttons_bottom = Box(
            name="pomodoro-buttons-bottom",
            spacing=8,
            h_align="center",
            children=[self.btn_reset, self.btn_reset_all],
        )

        self.children = [
            self.session_label,
            center_box,
            buttons_top,
            buttons_bottom,
        ]

        self._update_display()
        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, *_):
        self.timer_id = None

    def _get_current_duration(self) -> int:
        """Get total duration of current session."""
        if self.is_work_session:
            return self.work_duration
        else:
            is_long_break = (
                self.completed_sessions % self.sessions_until_long_break == 0
            )
            return self.long_break if is_long_break else self.short_break

    def _get_time_left(self) -> int:
        """Get remaining seconds."""
        return max(0, self._get_current_duration() - self.elapsed)

    def _get_progress(self) -> float:
        """Get progress as ratio 0.0-1.0."""
        duration = self._get_current_duration()
        return min(1.0, self.elapsed / duration) if duration > 0 else 0.0

    def _get_session_phase(self) -> str:
        """Get human-readable phase."""
        if self.is_work_session:
            return "Work"
        else:
            is_long = self.completed_sessions % self.sessions_until_long_break == 0
            return "Long Break" if is_long else "Short Break"

    def _update_display(self):
        """Update all display elements."""
        time_left = self._get_time_left()
        mins = time_left // 60
        secs = time_left % 60
        self.timer_label.set_markup(
            f"<span font='38' color='#f0d0d0'>{mins:02d}:{secs:02d}</span>"
        )

        phase = self._get_session_phase()
        self.phase_label.set_markup(f"<span font='12' color='#ffffff'>{phase}</span>")

        self.session_label.set_markup(
            f"<span font='11' color='#cccccc'>"
            f"Session {self.session_count}/{self.sessions_until_long_break * 2}</span>"
        )

        self.progress.set_progress(self._get_progress())

        # Update button state
        btn_label = (
            f"{self._icon_pause} Pause"
            if self.is_running
            else f"{self._icon_play} Start"
        )
        self.btn_pause.set_label(btn_label)

    def _tick(self) -> bool:
        """Timer tick callback."""
        self.elapsed += 1

        if self.elapsed >= self._get_current_duration():
            self._transition_phase()
            return False

        self._update_display()
        return True

    def _transition_phase(self):
        """Move to next phase."""
        if self.is_work_session:
            self.completed_sessions += 1
            self.is_work_session = False
        else:
            self.is_work_session = True
            self.session_count += 1

        self.elapsed = 0
        self.is_running = True
        self._update_display()
        self.timer_id = self._register_repeater(GLib.timeout_add(1000, self._tick))

    def start(self):
        """Start timer."""
        if self.is_running:
            return

        self.is_running = True
        self._update_display()
        self.timer_id = self._register_repeater(GLib.timeout_add(1000, self._tick))

    def pause(self):
        """Pause timer."""
        if not self.is_running:
            return

        self.is_running = False
        self._update_display()

        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

    def skip(self):
        """Skip to next phase."""
        self.pause()
        self._transition_phase()

    def reset(self):
        """Reset current session."""
        self.pause()
        self.elapsed = 0
        self._update_display()

    def reset_all(self):
        """Reset all progress."""
        self.pause()
        self.elapsed = 0
        self.session_count = 1
        self.completed_sessions = 0
        self.is_work_session = True
        self._update_display()

    def _on_pause_click(self, *_):
        """Toggle pause/start."""
        if self.is_running:
            self.pause()
        else:
            self.start()

    def _on_skip_click(self, *_):
        """Skip to next phase."""
        self.skip()
        self.start()

    def _on_reset_click(self, *_):
        """Reset current session."""
        self.reset()

    def _on_reset_all_click(self, *_):
        """Reset all progress."""
        self.reset_all()

    def close(self, *_):
        if self._parent is not None:
            self._parent.hide_popover()


class PomodoroWidget(ButtonWidget, PopoverMixin):
    """Panel widget that opens pomodoro timer popover."""

    def __init__(self, **kwargs):
        super().__init__(name="pomodoro", **kwargs)

        self.add_panel_content(
            self.config.get("icon", "🍅"),
            self.config.get("label_text", "Pomo"),
            show_label=self.config.get("label", True),
        )

        self.set_tooltip_if_enabled(_("widget.pomodoro.tooltip"), default=True)

        self.setup_popover(lambda: PomodoroMenu(parent=self))

from fabric.utils import GLib, Gtk, math
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.flowbox import FlowBox
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

from shared.widget_container import BoxWidget, ButtonWidget
from utils.i18n import _
from utils.icons import get_text_icon
from utils.widget_utils import nerd_font_icon

# ── Data ─────────────────────────────────────────────────────────────────────

EXERCISES = [
    dict(
        id="equal",
        name="Equal Breathing",
        description="Equal inhale and exhale",
        inhale=4,
        hold=0,
        exhale=4,
        hold2=0,
        cycles=6,
    ),
    dict(
        id="box",
        name="Box Breathing",
        description="Navy SEAL technique",
        inhale=4,
        hold=4,
        exhale=4,
        hold2=4,
        cycles=4,
    ),
    dict(
        id="478",
        name="4-7-8 Breathing",
        description="Calming technique for sleep",
        inhale=4,
        hold=7,
        exhale=8,
        hold2=0,
        cycles=4,
    ),
    dict(
        id="resonance",
        name="Resonance",
        description="5.5-5.5 breathing rhythm",
        inhale=5.5,
        hold=0,
        exhale=5.5,
        hold2=0,
        cycles=6,
    ),
]

TIME_PRESETS = [1, 2, 3, 5, 10, 15, 20]

PHASE_LABELS = {
    "inhale": ("Breathe In", "↑"),
    "hold": ("Hold", "—"),
    "exhale": ("Breathe Out", "↓"),
    "hold2": ("Hold", "—"),
}

# ── Animated breath circle ────────────────────────────────────────────────────


class BreathCircle(Gtk.DrawingArea):
    """A custom widget that visually represents the breathing cycle."""

    def __init__(self):
        super().__init__()
        self._phase = ""
        self._radius_frac = 0.32
        self.set_size_request(110, 110)
        self.connect("draw", self._on_draw)

    def update(self, phase: str, progress: float):
        self._phase = phase
        if phase == "inhale":
            self._radius_frac = 0.28 + 0.37 * progress
        elif phase == "hold":
            self._radius_frac = 0.65
        elif phase == "exhale":
            self._radius_frac = 0.65 - 0.37 * progress
        elif phase == "hold2":
            self._radius_frac = 0.28
        else:
            self._radius_frac = 0.32
        self.queue_draw()

    def _on_draw(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        cx, cy = w / 2, h / 2

        # outer dim ring
        cr.set_source_rgba(0.54, 0.71, 0.98, 0.15)
        cr.arc(cx, cy, min(w, h) / 2 * 0.90, 0, 2 * math.pi)
        cr.fill()

        # main pulsing circle
        r = min(w, h) / 2 * self._radius_frac
        if self._phase in ("inhale", "hold"):
            cr.set_source_rgba(0.54, 0.71, 0.98, 0.85)
        elif self._phase in ("exhale", "hold2"):
            cr.set_source_rgba(0.37, 0.56, 0.95, 0.60)
        else:
            cr.set_source_rgba(0.54, 0.71, 0.98, 0.28)

        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.fill()


# ── Exercise tile ─────────────────────────────────────────────────────────────


class ExerciseTile(Button):
    """A clickable tile representing a breathing exercise."""

    def __init__(self, exercise: dict, index: int, on_select):
        super().__init__()
        self._index = index
        self._on_select = on_select

        self.get_style_context().add_class("exercise-btn")
        self.set_size_request(170, 88)
        self.set_relief(Gtk.ReliefStyle.NONE)

        vbox = Box(
            orientation="vertical",
            spacing=3,
            margin_top=10,
            margin_bottom=10,
            margin_start=12,
            margin_end=12,
        )

        name = Label(
            label=exercise["name"],
            style_classes="exercise-name",
            h_align="start",
            ellipsization="end",
        )

        timing = f"{exercise['inhale']}-{exercise['hold']}-{exercise['exhale']}"
        tim_lbl = Label(label=timing, style_classes="exercise-timing", halign="start")

        desc = Label(
            label=exercise["description"],
            style_classes="exercise-desc",
            h_align="start",
            ellipsization="end",
            max_chars_width=24,
        )

        vbox.pack_start(name, False, False, 0)
        vbox.pack_start(tim_lbl, False, False, 0)
        vbox.pack_start(desc, False, False, 0)
        self.add(vbox)

        self.connect("clicked", lambda _: self._on_select(self._index))

    def set_active(self, active: bool):
        ctx = self.get_style_context()
        if active:
            ctx.add_class("active")
        else:
            ctx.remove_class("active")


class BreathingMenu(BoxWidget):
    """The main window for the breathing exercise widget."""

    def __init__(self):
        super().__init__(name="breathe-box", v_expand=True)
        self.set_size_request(-1, 540)
        # State
        self._current_index = 0
        self._selected_duration = 5
        self._is_running = False
        self._is_paused = False
        self._phase = ""
        self._phase_remaining = 0
        self._phase_total = 0
        self._total_remaining = 0
        self._current_cycle = 0
        self._total_cycles = 0
        self._timer_id = None

        self._build_ui()
        self.connect("destroy", lambda *_: self._stop_exercise())
        self._select_exercise(0)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = Box(orientation="vertical", spacing=0)

        # Header
        hbar = Box(orientation="horizontal", spacing=0, style_classes="header-bar")
        hbar.set_size_request(-1, 48)

        title_col = Box(
            orientation="vertical",
            spacing=1,
            v_align="center",
            h_expand=True,
            h_align="center",
        )

        self._subtitle_lbl = Label(label="", style_classes="subtittle-label")

        title_col.pack_start(self._subtitle_lbl, False, False, 0)
        hbar.pack_start(title_col, True, True, 12)
        outer.pack_start(hbar, False, False, 0)

        # Scrollable content
        scroll = ScrolledWindow(
            v_expand=True,
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
        )

        content = Box(
            orientation="vertical",
            spacing=14,
            margin_top=16,
            margin_bottom=16,
            margin_start=16,
            margin_end=16,
        )

        # Status card (click to pause)
        self._status_card = EventBox(style_classes="status-card")
        self._status_card.connect("button-press-event", lambda *_: self._toggle_pause())

        card_inner = Box(
            orientation="horizontal",
            spacing=14,
            margin_top=14,
            margin_bottom=14,
            margin_start=14,
            margin_end=14,
        )

        self._circle = BreathCircle()
        card_inner.pack_start(self._circle, False, False, 0)

        text_col = Box(orientation="vertical", spacing=2, v_align="center")

        self._phase_label = Label(
            label="—", style_classes="phase-label", h_align="start"
        )

        self._countdown_label = Label(
            label="", style_classes="countdown-label", h_align="start"
        )

        self._total_label = Label(
            label=_("widget.breathing.select_exercise"),
            style_classes="info-label",
            h_align="start",
        )

        self._cycle_label = Label(label="", style_classes="info-label", h_align="start")

        text_col.pack_start(self._phase_label, False, False, 0)
        text_col.pack_start(self._countdown_label, False, False, 0)
        text_col.pack_start(self._total_label, False, False, 0)
        text_col.pack_start(self._cycle_label, False, False, 0)

        card_inner.pack_start(text_col, True, True, 0)
        self._status_card.add(card_inner)
        content.pack_start(self._status_card, False, False, 0)

        # Exercise grid
        self._grid_frame = Box(orientation="vertical", spacing=8)

        grid_lbl = Label(
            label=_("widget.breathing.choose_exercise"),
            style_classes="section-label",
            h_align="start",
        )
        self._grid_frame.pack_start(grid_lbl, False, False, 0)

        grid = FlowBox(
            column_spacing=8,
            row_spacing=8,
            homogeneous=True,
            min_children_per_line=2,
            max_children_per_line=2,
        )

        grid.set_selection_mode(Gtk.SelectionMode.NONE)

        self._tiles: list[ExerciseTile] = []
        for i, ex in enumerate(EXERCISES):
            tile = ExerciseTile(ex, i, self._select_exercise)
            self._tiles.append(tile)
            grid.add(tile)

        self._grid_frame.pack_start(grid, False, False, 0)
        content.pack_start(self._grid_frame, False, False, 0)

        # Duration presets
        self._duration_frame = Box(orientation="vertical", spacing=6)

        dur_lbl = Label(
            label=_("widget.breathing.duration"),
            style_classes="section-label",
            h_align="start",
        )
        self._duration_frame.pack_start(dur_lbl, False, False, 0)

        dur_row = Box(orientation="horizontal", spacing=8)

        dur_adj = Gtk.Adjustment(
            value=self._selected_duration,
            lower=1,
            upper=60,
            step_increment=1,
            page_increment=5,
        )
        self._dur_spin = Gtk.SpinButton(
            adjustment=dur_adj, climb_rate=1, digits=0, valign=Gtk.Align.CENTER
        )
        self._dur_spin.get_style_context().add_class("dur-spin")
        self._dur_spin.connect("value-changed", self._on_spin_value_changed)

        dur_unit = Label(label=_("widget.breathing.min"), style_classes="section-label")

        dur_row.pack_start(self._dur_spin, True, True, 0)
        dur_row.pack_start(dur_unit, False, False, 0)

        self._duration_frame.pack_start(dur_row, False, False, 0)
        content.pack_start(self._duration_frame, False, False, 0)

        # Start / Stop buttons
        btn_row = Box(orientation="horizontal", spacing=8)

        self._start_btn = Button(
            label=_("widget.breathing.start"),
            style_classes="start-btn",
            h_expand=True,
            on_clicked=self._on_start_clicked,
        )
        btn_row.pack_start(self._start_btn, True, True, 0)

        self._stop_btn = Button(
            label=_("widget.breathing.stop"),
            style_classes="stop-btn",
            h_expand=True,
            sensitive=False,
            on_clicked=self._stop_exercise,
        )
        btn_row.pack_start(self._stop_btn, True, True, 0)

        content.pack_start(btn_row, False, False, 0)

        scroll.add(content)
        outer.pack_start(scroll, True, True, 0)
        self.add(outer)

    # ── Exercise selection ────────────────────────────────────────────────────

    def _select_exercise(self, index: int):
        self._current_index = index
        for i, tile in enumerate(self._tiles):
            tile.set_active(i == index)
        if not self._is_running:
            self._update_display()

    # ── Timer logic ───────────────────────────────────────────────────────────

    def _start_exercise(self):
        ex = EXERCISES[self._current_index]
        cycle_secs = ex["inhale"] + ex["hold"] + ex["exhale"] + ex["hold2"]
        self._total_cycles = max(1, int((self._selected_duration * 60) / cycle_secs))
        self._current_cycle = 1
        self._phase = "inhale"
        self._phase_remaining = int(ex["inhale"] * 1000)
        self._phase_total = self._phase_remaining
        self._total_remaining = self._selected_duration * 60 * 1000
        self._is_running = True
        self._is_paused = False
        self._schedule_tick()
        self._update_display()

    def _stop_exercise(self, *_):
        self._is_running = False
        self._is_paused = False
        self._phase = ""
        self._phase_remaining = 0
        self._phase_total = 0
        self._total_remaining = 0
        self._current_cycle = 0
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        self._update_display()

    def _toggle_pause(self):
        if not self._is_running:
            return
        self._is_paused = not self._is_paused
        if self._is_paused:
            if self._timer_id is not None:
                GLib.source_remove(self._timer_id)
                self._timer_id = None
        else:
            self._schedule_tick()
        self._update_display()

    def _schedule_tick(self):
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
        self._timer_id = GLib.timeout_add(1000, self._tick)

    def _tick(self):
        self._timer_id = None
        if not self._is_running or self._is_paused:
            return False

        self._phase_remaining -= 1000
        self._total_remaining -= 1000

        if self._total_remaining <= 0:
            self._stop_exercise()
            self._show_info("Exercise complete! 🎉")
            return False

        if self._phase_remaining <= 0:
            self._advance_phase()

        self._update_display()
        self._schedule_tick()

        return False

    def _advance_phase(self):
        ex = EXERCISES[self._current_index]

        def go(phase, secs):
            self._phase = phase
            self._phase_remaining = int(secs * 1000)
            self._phase_total = self._phase_remaining

        if self._phase == "inhale":
            go("hold", ex["hold"]) if ex["hold"] > 0 else go("exhale", ex["exhale"])
        elif self._phase == "hold":
            go("exhale", ex["exhale"])
        elif self._phase == "exhale":
            if ex["hold2"] > 0:
                go("hold2", ex["hold2"])
            else:
                self._next_cycle(ex)
        elif self._phase == "hold2":
            self._next_cycle(ex)

    def _next_cycle(self, ex):
        if self._current_cycle < self._total_cycles:
            self._current_cycle += 1
            self._phase = "inhale"
            self._phase_remaining = int(ex["inhale"] * 1000)
            self._phase_total = self._phase_remaining
        else:
            self._stop_exercise()
            self._show_info("Exercise complete! 🎉")

    # ── UI update ─────────────────────────────────────────────────────────────

    def _update_display(self):
        ex = EXERCISES[self._current_index]

        if self._is_running and self._phase:
            if self._is_paused:
                phase_text, arrow = "Paused", "⏸"
            else:
                phase_text, arrow = PHASE_LABELS.get(self._phase, ("—", ""))

            secs = math.ceil(self._phase_remaining / 1000)
            total_m = self._total_remaining // 60000
            total_s = (self._total_remaining % 60000) // 1000
            progress = (
                1.0 - (self._phase_remaining / self._phase_total)
                if self._phase_total
                else 0
            )

            self._phase_label.set_text(f"{arrow}  {phase_text}")
            self._countdown_label.set_text(f"{secs}s")
            self._total_label.set_text(f"{total_m}:{total_s:02d} remaining")
            self._cycle_label.set_text(
                f"Cycle {self._current_cycle} / {self._total_cycles}  •  {ex['name']}"
            )
            self._circle.update(self._phase if not self._is_paused else "", progress)
            self._subtitle_lbl.set_text(ex["name"])

            self._grid_frame.set_visible(False)
            self._duration_frame.set_visible(False)
            label = "⏸  Pause" if not self._is_paused else "▶  Resume"
            self._start_btn.set_label(label)
            self._stop_btn.set_sensitive(True)

        else:
            self._phase_label.set_text("—")
            self._countdown_label.set_text("")
            self._total_label.set_text(_("widget.breathing.select_exercise"))
            self._cycle_label.set_text("")
            self._circle.update("", 0)
            self._subtitle_lbl.set_text("")

            self._grid_frame.set_visible(True)
            self._duration_frame.set_visible(True)
            self._start_btn.set_label(_("widget.breathing.start"))
            self._stop_btn.set_sensitive(False)

        self.show_all()

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_start_clicked(self, _btn):
        if self._is_running:
            self._toggle_pause()
        else:
            self._start_exercise()

    def _on_spin_value_changed(self, spin):
        self._selected_duration = int(spin.get_value())

    def _on_duration_clicked(self, btn, minutes):
        self._selected_duration = minutes
        for b in self._dur_buttons:
            b.get_style_context().remove_class("active")
        btn.get_style_context().add_class("active")

    def _show_info(self, message: str):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=message,
        )
        dialog.run()
        dialog.destroy()


class BreatheWidget(ButtonWidget):
    """A widget to guide users through breathing exercises."""

    def __init__(self, **kwargs):
        super().__init__(name="breathe", **kwargs)

        self.popup = None

        self.connect("clicked", self.on_click)

        self.label = Label(
            label=_("widget.breathing.label"), style_classes="breathe-label"
        )
        self.icon = nerd_font_icon(
            icon=get_text_icon("notifications.noisy", "󰂜"),
            props={
                "style_classes": ["panel-font-icon"],
            },
        )

        self.container_box.add(self.label)

    def on_click(self, *_):
        if self.popup is None:
            from shared.popover import Popover

            self.popup = Popover(
                content=BreathingMenu(),
                point_to=self,
            )
            self.popup.connect(
                "popover-closed", lambda *_: self.remove_style_class("active")
            )
            self.popup.open()

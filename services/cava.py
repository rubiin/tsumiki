"""cava (console audio visualizer) as a shared source of audio levels.

Consumers ask for levels with ``set_wanted(owner, True)`` and withdraw with
``set_wanted(owner, False)``; cava runs only while at least one still wants
them, so an idle bar costs no process.
"""

import os

from fabric.core.service import Signal
from fabric.utils import Gio, GLib, logger

from utils.constants import CAVA_CONFIG
from utils.functions import find_executable

from .base import SingletonService


class CavaService(SingletonService):
    """Runs cava while someone wants bars, reading its raw ASCII output.

    Each frame is one line of values 0-1000 separated by ``;``; the parsed
    levels are exposed as ``bars`` (one float per bar, 0.0-1.0).
    """

    def make_config(
        self,
        bars,
        framerate,
        noise_reduction,
        bar_width,
        bar_gap,
        high_cutoff,
        low_cutoff,
        source,
        monstercat,
        input,
    ) -> str:
        return f"""[general]
bars = {bars}
framerate = {framerate}
autosens = 1
bar_width = {bar_width}
bar_spacing = {bar_gap}
higher_cutoff_freq = {high_cutoff}
lower_cutoff_freq = {low_cutoff}

[input]
method = {input}
source = {source}

[output]
method = raw
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = 1000
bar_delimiter = 59
frame_delimiter = 10

[smoothing]
noise_reduction = {noise_reduction}
monstercat = {monstercat}
"""

    @Signal
    def frame(self) -> None:
        """Signal emitted with every new set of levels."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bars: list[float] = [0.0] * 64
        self._bar_count = 64
        self.available = find_executable("cava") is not None
        self._process: Gio.Subprocess | None = None
        self._stream: Gio.DataInputStream | None = None
        self._cancellable: Gio.Cancellable | None = None
        self._wanted_by: set[str] = set()
        self._config: dict = {}

    @property
    def running(self) -> bool:
        return self._process is not None

    def set_wanted(self, owner: str, wanted: bool, config: dict | None = None) -> None:
        """Ask for levels (or stop asking); cava runs while anyone asks."""
        if wanted:
            self._wanted_by.add(owner)
            if config is not None:
                self._config = config
        else:
            self._wanted_by.discard(owner)
        if self._wanted_by and not self.running:
            self.start(self._config)
        elif not self._wanted_by and self.running:
            self.stop()

    def _write_config(self, config: dict) -> None:
        os.makedirs(os.path.dirname(CAVA_CONFIG), exist_ok=True)
        with open(CAVA_CONFIG, "w") as f:
            f.write(
                self.make_config(
                    bars=config.get("bars", 64),
                    framerate=config.get("framerate", 60),
                    noise_reduction=config.get("noise_reduction", 77),
                    bar_width=config.get("bar_width", 2),
                    bar_gap=config.get("bar_gap", 1),
                    high_cutoff=config.get("high_cutoff", 10000),
                    low_cutoff=config.get("low_cutoff", 50),
                    source=config.get("source", "auto"),
                    monstercat=config.get("monstercat", 0),
                    input=config.get("input", "pipewire"),
                )
            )

    def start(self, config: dict | None = None) -> None:
        if self.running or not self.available:
            return
        config = config or {}
        self._bar_count = max(1, int(config.get("bars", 64)))
        self.bars = [0.0] * self._bar_count
        try:
            self._write_config(config)
            self._process = Gio.Subprocess.new(
                ["cava", "-p", CAVA_CONFIG],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except (GLib.Error, OSError) as e:
            logger.warning(f"[Cava] Couldn't start cava: {e}")
            self.available = False
            self._process = None
            return
        pipe = self._process.get_stdout_pipe()
        if pipe is None:
            self.stop()
            return
        self._stream = Gio.DataInputStream.new(pipe)
        self._cancellable = Gio.Cancellable()
        self._read_next()

    def stop(self) -> None:
        if self._cancellable is not None:
            self._cancellable.cancel()
        if self._process is not None:
            self._process.force_exit()
        self._process = None
        self._stream = None
        self._cancellable = None
        self.bars = [0.0] * self._bar_count
        self.frame()

    def _read_next(self) -> None:
        if self._stream is None:
            return
        self._stream.read_line_async(
            GLib.PRIORITY_DEFAULT, self._cancellable, self._on_line
        )

    def _parse_line(self, line: str) -> list[float] | None:
        values = [v for v in line.split(";") if v]
        if len(values) < self._bar_count:
            return None
        try:
            return [int(v) / 1000 for v in values[: self._bar_count]]
        except ValueError:
            return None

    def _on_line(self, stream: Gio.DataInputStream, result: Gio.AsyncResult) -> None:
        try:
            line, _length = stream.read_line_finish_utf8(result)
        except GLib.Error:
            return  # cancelled or the process went away
        if line is None:
            self.stop()
            return
        bars = self._parse_line(line)
        if bars is not None:
            self.bars = bars
            self.frame()
        self._read_next()


cava_service = CavaService()

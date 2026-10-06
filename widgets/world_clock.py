from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fabric.utils import logger
from fabric.widgets.label import Label

from shared.widget_container import ButtonWidget


class WorldClockWidget(ButtonWidget):
    """a widget that displays the title of the active window."""

    def __init__(self, **kwargs):
        super().__init__(name="world_clock", **kwargs)

        self.clocks = []

        self.label_format = self.config.get("label_format", "󰌌")
        self.add_formatted_label(self.label_format)

        self.container_box.set_spacing(10)

        timezones = self.config.get("timezones", [])

        self.is_24hr = self.config.get("use_24hr", True)
        self.time_format = "%H:%M:%S" if self.is_24hr else "%I:%M:%S %p"

        for tz_name in timezones:
            # ZoneInfo raises on an unknown key; scanning the zoneinfo database
            # to validate one or two names costs the bar its construction time.
            try:
                tz = ZoneInfo(tz_name)
            except (ZoneInfoNotFoundError, ValueError):
                logger.info(f"[world_clock] Skipping invalid timezone: {tz_name}")
                continue
            label = Label(style_classes="world-clock-label")
            self.container_box.pack_start(label, True, True, 0)
            self.clocks.append((label, tz))

        # Fill the labels now: the first tick is up to a minute away, and an
        # empty label reads as a broken widget.
        self._update_ui()
        self._arm_minute_timer()

    def _arm_minute_timer(self) -> None:
        """Schedule the next update on a minute boundary, not 60 s from now."""
        now = datetime.now()
        delay_ms = 60_000 - (now.second * 1000 + now.microsecond // 1000)
        self._add_repeater(max(1000, delay_ms), self._on_minute)

    def _on_minute(self) -> bool:
        self._update_ui()
        # Re-align: a tick that fired late must not push every later one back.
        self._arm_minute_timer()
        return False

    def _update_ui(self):
        try:
            utc_now = datetime.now(timezone.utc)
            for label, tz in self.clocks:
                local_time = utc_now.astimezone(tz)
                abbrev = local_time.tzname()
                formatted = local_time.strftime(self.time_format)
                label.set_text(f"{abbrev}: {formatted}")
        except Exception as e:
            logger.exception(f"[world_clock] Failed to update UI: {e}")

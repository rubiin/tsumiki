import time
from datetime import datetime

from fabric.core.service import Property
from fabric.widgets.datetime import DateTime
from nepali.datetime import nepalidatetime


class ExtendedDateTime(DateTime):
    """DateTime that renders in the Nepali (Bikram Sambat) calendar."""

    @Property(bool, "read-write", default_value=False)
    def nepali_time(self):
        return self._nepali_time

    @nepali_time.setter
    def nepali_time(self, value: bool):
        self._set_nepali_time(value)

    def __init__(self, nepali_time: bool = False, **kwargs):
        # Set before super(), which renders the label while initialising.
        self._nepali_time = nepali_time
        super().__init__(**kwargs)

    def toggle_calendar(self) -> bool:
        """Flip between the Gregorian and the Nepali calendar."""
        self._set_nepali_time(not self._nepali_time)
        return self._nepali_time

    def _set_nepali_time(self, value: bool) -> None:
        self._nepali_time = value
        self.do_update_label()

    def do_format(self) -> str:
        if self._nepali_time:
            nepali_now = nepalidatetime.from_datetime(datetime.now())
            return nepali_now.strftime(self._formatters[self._current_index])
        return time.strftime(self._formatters[self._current_index])

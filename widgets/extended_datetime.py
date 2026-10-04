import time
from datetime import datetime

from fabric.widgets.datetime import DateTime
from nepali.datetime import nepalidatetime


class ExtendedDateTime(DateTime):
    """DateTime that can render the Nepali (Bikram Sambat) calendar.

    Starts on the Gregorian calendar; ``toggle_calendar`` flips it.
    """

    _nepali_time = False

    def toggle_calendar(self) -> bool:
        """Flip between the Gregorian and the Nepali calendar."""
        self._nepali_time = not self._nepali_time
        self.do_update_label()
        return self._nepali_time

    def do_format(self) -> str:
        if self._nepali_time:
            nepali_now = nepalidatetime.from_datetime(datetime.now())
            return nepali_now.strftime(self._formatters[self._current_index])
        return time.strftime(self._formatters[self._current_index])

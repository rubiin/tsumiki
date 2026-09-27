import time
from datetime import datetime

from fabric.widgets.datetime import DateTime
from nepali.datetime import nepalidatetime


class ExtendedDateTime(DateTime):
    """DateTime that renders in the Nepali (Bikram Sambat) calendar."""

    def __init__(self, nepali_time: bool = False, **kwargs):
        self._nepali_time = nepali_time
        super().__init__(**kwargs)

    def do_format(self) -> str:
        if self._nepali_time:
            nepali_now = nepalidatetime.from_datetime(datetime.now())
            return nepali_now.strftime(self._formatters[self._current_index])
        return time.strftime(self._formatters[self._current_index])

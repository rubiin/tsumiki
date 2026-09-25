import random
from typing import Callable, Optional

from fabric.utils import logger, os, time

from utils.constants import QUOTES_CACHE_FILE
from utils.decorators import run_worker_with_idle
from utils.functions import read_json_file, write_json_file

from .base import SingletonService


class QuotesService(SingletonService):
    """Lightweight singleton to fetch and cache quotes from ZenQuotes API."""

    __slots__ = ("api_url", "cache_file")  # prevents __dict__ memory

    def __init__(
        self,
    ):
        super().__init__()
        self.api_url = "https://zenquotes.io/api/quotes"

    def simple_quotes_info(
        self, retries: int = 3, delay: float = 2.0
    ) -> Optional[dict]:
        from utils.functions import get_http_client

        session = get_http_client()
        for attempt in range(retries):
            try:
                response = session.get(self.api_url, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.warning(
                    f"[Quotes] Fetch failed (attempt {attempt + 1}/{retries}): {e}"
                )
                time.sleep(delay * (attempt + 1))
        return None

    def get_quotes(self, ttl: int = 3600) -> Optional[dict]:
        quotes = None

        if os.path.exists(QUOTES_CACHE_FILE):
            cache_age = time.time() - os.path.getmtime(QUOTES_CACHE_FILE)
            if cache_age < ttl:
                quotes = read_json_file(QUOTES_CACHE_FILE)
                return random.choice(quotes) if quotes else None
            # Cache expired — refresh from the API.

        quotes = self.simple_quotes_info()
        if quotes:
            write_json_file(QUOTES_CACHE_FILE, quotes)

        return random.choice(quotes) if quotes else None

    def get_quotes_async(
        self,
        callback: Callable[[Optional[dict]], None],
    ):
        run_worker_with_idle(self.get_quotes, callback)

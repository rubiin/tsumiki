"""Tests for :class:`utils.ttl_cache.TTLCache`.

The clock is injected so expiry is tested without sleeping.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.ttl_cache import CACHE_MISS, TTLCache


class FakeClock:
    """A monotonic clock the test advances by hand."""

    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_cache(maxsize: int = 128, default_ttl: float | None = None):
    clock = FakeClock()
    return TTLCache(maxsize=maxsize, default_ttl=default_ttl, clock=clock), clock


class GetPutTests(unittest.TestCase):
    """Reading, writing, and the TTLs that mean "do not cache"."""

    def test_a_miss_returns_the_sentinel(self):
        cache, _ = make_cache()
        self.assertIs(cache.get("k"), CACHE_MISS)
        self.assertEqual("fallback", cache.get("k", "fallback"))

    def test_roundtrip(self):
        cache, _ = make_cache(default_ttl=10)
        cache.put("k", {"a": 1})
        self.assertEqual({"a": 1}, cache.get("k"))

    def test_a_cached_none_is_still_a_hit(self):
        """None is a value plugins legitimately cache; a sentinel miss is the
        only way to tell 'absent' from 'cached None'."""
        cache, _ = make_cache(default_ttl=10)
        cache.put("k", None)
        self.assertIsNone(cache.get("k"))
        self.assertEqual(1, len(cache))

    def test_a_non_positive_ttl_is_not_cached(self):
        for ttl in (None, 0, -1):
            cache, _ = make_cache()
            cache.put("k", "v", ttl=ttl)
            self.assertIs(cache.get("k"), CACHE_MISS, ttl)

    def test_ttl_falls_back_to_the_default(self):
        cache, _ = make_cache(default_ttl=10)
        cache.put("k", "v")
        self.assertEqual(10, cache._entries["k"][0] - cache._clock())

    def test_an_explicit_ttl_overrides_the_default(self):
        cache, _ = make_cache(default_ttl=10)
        cache.put("k", "v", ttl=99)
        self.assertEqual(99, cache._entries["k"][0] - cache._clock())


class ExpiryTests(unittest.TestCase):
    """An entry is live until its own deadline, not a fixed one."""

    def test_an_entry_expires(self):
        cache, clock = make_cache(default_ttl=10)
        cache.put("k", "v")

        clock.advance(9.999)
        self.assertEqual("v", cache.get("k"))

        clock.advance(0.002)
        self.assertIs(cache.get("k"), CACHE_MISS)

    def test_reading_an_expired_entry_drops_it(self):
        cache, clock = make_cache(default_ttl=10)
        cache.put("k", "v")
        clock.advance(11)

        cache.get("k")

        self.assertEqual(0, len(cache))

    def test_reputting_refreshes_the_deadline(self):
        cache, clock = make_cache(default_ttl=10)
        cache.put("k", "v")
        clock.advance(8)
        cache.put("k", "v2")
        clock.advance(8)

        self.assertEqual("v2", cache.get("k"))


class EvictionTests(unittest.TestCase):
    """What gets dropped when the cache outgrows its cap."""

    def test_the_cache_stays_under_its_cap(self):
        cache, _ = make_cache(maxsize=8, default_ttl=1000)
        for i in range(100):
            cache.put(i, i)
        self.assertLessEqual(len(cache), 8)

    def test_the_newest_entries_survive(self):
        cache, _ = make_cache(maxsize=8, default_ttl=1000)
        for i in range(100):
            cache.put(i, i)
        for i in range(92, 100):
            self.assertEqual(i, cache.get(i), i)

    def test_expired_entries_are_dropped_before_live_ones(self):
        """Otherwise a burst of fresh keys evicts fresh entries while the
        expired ones it should have cleared are still there."""
        cache, clock = make_cache(maxsize=4, default_ttl=1000)
        for i in range(4):
            cache.put(f"stale{i}", i, ttl=5)
        clock.advance(10)
        for i in range(4):
            cache.put(f"fresh{i}", i, ttl=1000)

        for i in range(4):
            self.assertEqual(i, cache.get(f"fresh{i}"), f"fresh{i}")

    def test_invalidate_and_clear(self):
        cache, _ = make_cache(default_ttl=10)
        cache.put("k", "v")
        cache.invalidate("k")
        self.assertIs(cache.get("k"), CACHE_MISS)

        cache.put("k", "v")
        cache.put("j", "v")
        cache.clear()
        self.assertEqual(0, len(cache))


class GetOrProduceTests(unittest.TestCase):
    """get_or_produce is the stat/network-shaped caller."""

    def test_the_producer_runs_once_on_a_hit_path(self):
        cache, _ = make_cache(default_ttl=10)
        calls = []

        for _ in range(3):
            cache.get_or_produce("k", lambda: calls.append(1) or "v")

        self.assertEqual(1, len(calls))

    def test_the_produced_value_is_returned_and_stored(self):
        cache, _ = make_cache(default_ttl=10)
        self.assertEqual("v", cache.get_or_produce("k", lambda: "v"))
        self.assertEqual("v", cache.get("k"))

    def test_a_produced_value_is_not_cached_without_a_ttl(self):
        cache, _ = make_cache()
        calls = []

        for _ in range(2):
            cache.get_or_produce("k", lambda: calls.append(1) or "v")

        self.assertEqual(2, len(calls))

    def test_producer_raising_does_not_poison_the_cache(self):
        cache, _ = make_cache(default_ttl=10)

        def boom():
            raise ValueError("nope")

        with self.assertRaises(ValueError):
            cache.get_or_produce("k", boom)
        self.assertIs(cache.get("k"), CACHE_MISS)


if __name__ == "__main__":
    unittest.main()

"""Tests for ``utils/singleton.py``.

Eight classes used to hand-roll this; the mixin's contract is that construction
is idempotent and that a failed ``__init__`` stays retryable.
"""

import unittest

from utils.singleton import SingletonMixin


class Example(SingletonMixin):
    """Counts how often its initialisation body actually ran."""

    def __init__(self, value: int = 0):
        if not self._init_once():
            return
        self.inits = getattr(self, "inits", 0) + 1
        self.value = value


class Failing(SingletonMixin):
    """Raises on the first construction only."""

    attempts = 0

    def __init__(self):
        type(self).attempts += 1
        if type(self).attempts == 1:
            # Fails *after* the guard, so the retry is what proves the flag is
            # not set by a successful body.
            raise RuntimeError("boom")
        if not self._init_once():
            return
        self.ready = True


class SingletonMixinTest(unittest.TestCase):
    """One instance, one initialisation, and a working reset."""

    def setUp(self):
        for cls in (Example, Failing):
            cls.reset_instance()
            cls.attempts = 0
        self.addCleanup(Example.reset_instance)
        self.addCleanup(Failing.reset_instance)

    def test_repeat_construction_returns_one_instance(self):
        self.assertIs(Example(), Example())

    def test_init_runs_only_once(self):
        Example()
        Example()
        Example()

        self.assertEqual(1, Example().inits)

    def test_arguments_after_the_first_call_are_ignored(self):
        first = Example(value=1)
        second = Example(value=2)

        self.assertIs(first, second)
        self.assertEqual(1, second.value)

    def test_a_failing_init_stays_retryable(self):
        with self.assertRaises(RuntimeError):
            Failing()

        instance = Failing()

        self.assertTrue(instance.ready)
        self.assertEqual(2, Failing.attempts)

    def test_reset_instance_forgets_everything(self):
        first = Example()
        Example.reset_instance()

        self.assertIsNot(first, Example())

    def test_a_subclass_gets_its_own_instance(self):
        class Sub(Example):
            pass

        Sub.reset_instance()
        self.addCleanup(Sub.reset_instance)

        self.assertIsNot(Sub(), Example())


if __name__ == "__main__":
    unittest.main()

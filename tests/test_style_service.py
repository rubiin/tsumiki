"""Tests for StyleService CSS compilation scheduling.

The service is built with ``__new__`` so the scheduler can be exercised without
running sass or touching the real application.
"""

import os
import tempfile
import threading
import unittest
from unittest import mock

from services.style import StyleService
from tests.helpers import run_inline


def _make_service() -> StyleService:
    service = StyleService.__new__(StyleService)
    service._compile_lock = threading.Lock()
    service._compiling = False
    service._compile_pending = False
    service.emit = mock.Mock()
    return service


class CompileCoalescingTest(unittest.TestCase):
    """A refresh that lands mid-compile must be re-run, not dropped."""

    def test_refresh_during_compile_is_not_dropped(self):
        service = _make_service()
        dispatches = []

        def fake_compile_and_apply(dispatch):
            dispatches.append(dispatch)
            if len(dispatches) == 1:
                # A style change lands while this compile is in flight.
                service.refresh()

        with (
            mock.patch.object(
                service, "_compile_and_apply", side_effect=fake_compile_and_apply
            ),
            mock.patch("services.style.thread", side_effect=run_inline),
        ):
            service.refresh()

        self.assertEqual(len(dispatches), 2)
        self.assertFalse(service._compiling)
        self.assertFalse(service._compile_pending)

    def test_concurrent_refreshes_use_one_worker(self):
        service = _make_service()
        submitted = []

        def capture(target, *args, **kwargs):
            submitted.append(target)
            return mock.Mock()

        with mock.patch("services.style.thread", side_effect=capture):
            service.refresh()
            service.refresh()
            service.refresh()

        self.assertEqual(len(submitted), 1)
        self.assertTrue(service._compiling)

    def test_compile_failure_does_not_wedge_refresh(self):
        service = _make_service()

        with (
            mock.patch.object(
                service, "_compile_and_apply", side_effect=RuntimeError("boom")
            ),
            mock.patch("services.style.thread", side_effect=run_inline),
        ):
            service.refresh()

        self.assertFalse(service._compiling)

        # A later refresh must still schedule work.
        with (
            mock.patch.object(service, "_compile_and_apply") as compile_once,
            mock.patch("services.style.thread", side_effect=run_inline),
        ):
            service.refresh()

        compile_once.assert_called_once()


class BlockingRefreshTest(unittest.TestCase):
    """The startup path must compile and apply without deferring."""

    def test_refresh_blocking_applies_before_emitting(self):
        service = _make_service()
        order = []
        service._apply_css_to_app = mock.Mock(
            side_effect=lambda path: order.append(("apply", path))
        )
        service.emit = mock.Mock(side_effect=lambda *args: order.append(("emit", args)))

        with (
            mock.patch("services.style.exec_shell_command", return_value=""),
            mock.patch("services.style.idle_add") as idle,
            mock.patch(
                "services.style.get_relative_path", return_value="/tmp/main.css"
            ),
        ):
            service.refresh_blocking()

        idle.assert_not_called()
        self.assertEqual(order[0], ("apply", "/tmp/main.css"))
        self.assertEqual(order[1], ("emit", ("css_recompiled",)))

    def test_refresh_blocking_emits_even_when_sass_fails(self):
        service = _make_service()
        events = []
        service._apply_css_to_app = mock.Mock(
            side_effect=lambda path: events.append(("apply", path))
        )
        service.emit = mock.Mock(
            side_effect=lambda *args: events.append(("emit", args))
        )

        with (
            mock.patch("services.style.exec_shell_command", return_value="Error: nope"),
            mock.patch(
                "services.style.get_relative_path", return_value="/tmp/main.css"
            ),
        ):
            service.refresh_blocking()

        # A broken compile clears the stylesheet but listeners still hear the apply.
        self.assertEqual(events, [("apply", ""), ("emit", ("css_recompiled",))])


class AsyncApplyEmitOrderTest(unittest.TestCase):
    """The async path must announce the apply only after it has run."""

    def test_async_emit_follows_the_applied_stylesheet(self):
        service = _make_service()
        events = []
        service._apply_css_to_app = mock.Mock(
            side_effect=lambda path: events.append(("apply", path))
        )
        service.emit = mock.Mock(
            side_effect=lambda *args: events.append(("emit", args))
        )
        deferred = []

        with (
            mock.patch("services.style.exec_shell_command", return_value=""),
            mock.patch(
                "services.style.idle_add",
                side_effect=lambda *args: deferred.append(args),
            ),
            mock.patch(
                "services.style.get_relative_path", return_value="/tmp/main.css"
            ),
            mock.patch("services.style.thread", side_effect=run_inline),
        ):
            service.refresh()

        # The worker only queues the apply; nothing is announced yet.
        self.assertEqual(events, [])
        self.assertEqual(len(deferred), 1)

        callback, *args = deferred[0]
        callback(*args)

        self.assertEqual(
            events,
            [("apply", "/tmp/main.css"), ("emit", ("css_recompiled",))],
        )


class CharsetStripTest(unittest.TestCase):
    """``--no-charset`` already prevents this; the apply must not re-check the
    whole stylesheet to find out."""

    def test_a_charset_free_file_is_read_once_and_never_rewritten(self):
        css = "body { color: red; }\n"

        with mock.patch("builtins.open", mock.mock_open(read_data=css)) as opener:
            StyleService._apply_css_to_app("main.css")

        opener.assert_called_once_with("main.css", encoding="utf-8")
        self.assertEqual(0, opener.return_value.write.call_count)

    def test_a_charset_line_is_still_stripped_when_it_is_there(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "main.css")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('@charset "UTF-8";\nbody { color: red; }\n')

            StyleService._apply_css_to_app(path)

            with open(path, encoding="utf-8") as handle:
                rewritten = handle.read()

        self.assertNotIn("@charset", rewritten)
        self.assertIn("body { color: red; }", rewritten)


if __name__ == "__main__":
    unittest.main()

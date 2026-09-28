"""Startup ordering in ``main.py``.

The first ``sass`` compile is deliberately inline, so the data directory has to
exist before it runs: an off-thread ``mkdir`` can lose the race and leave the
bar mapped unstyled.
"""

import os
import tempfile
import unittest
from unittest import mock

import main as main_module
import services


class StartupOrderingTest(unittest.TestCase):
    """``ensure_directory`` must complete before the styles are compiled."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.data_dir = os.path.join(self._tmpdir.name, "tsumiki")

        self.sync_flags: list[bool] = []
        self.existed_at_compile: list[bool] = []
        self.deferred: str | None = None

        self._patch_attr(main_module, "APP_DATA_DIRECTORY", self.data_dir)
        self._patch_attr(main_module.helpers, "ensure_directory", self._ensure)
        # main() imports the lazy proxy inside the function, so patch its source.
        self._patch_attr(services, "style_service", self._fake_style_service())

    def _patch_attr(self, target, name, replacement):
        patcher = mock.patch.object(target, name, replacement)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _fake_style_service(self):
        return mock.Mock(
            refresh_blocking=mock.Mock(side_effect=self._compile),
            write_settings_css=mock.Mock(),
            apply_theme_from_config=mock.Mock(),
        )

    def _ensure(self, path, *, sync=False):
        """Mimic the writer: inline when sync, otherwise on an unscheduled thread."""
        self.sync_flags.append(sync)
        if sync:
            os.makedirs(path, exist_ok=True)
        else:
            self.deferred = path

    def _compile(self):
        self.existed_at_compile.append(os.path.isdir(self.data_dir))

    def _run_main(self) -> None:
        """Run ``main()`` with the app, the bar and the process rename stubbed."""
        for name, replacement in (
            ("Application", mock.Mock()),
            ("Bar", mock.Mock()),
            # An empty config keeps the module registry from building real windows.
            ("tsumiki_config", mock.Mock(**{"get.return_value": {}})),
        ):
            self._patch_attr(main_module, name, replacement)
        self._patch_attr(main_module.helpers, "set_process_name", mock.Mock())
        watcher = mock.patch("utils.config_watcher.start_config_watching")
        self.addCleanup(watcher.stop)
        watcher.start()

        main_module.main()

    def test_the_data_directory_is_created_synchronously(self):
        self._run_main()

        self.assertEqual([True], self.sync_flags)

    def test_the_directory_exists_when_the_styles_are_compiled(self):
        """Regression: a late mkdir made the compile fail and the bar unstyled."""
        self._run_main()

        self.assertEqual([True], self.existed_at_compile)


if __name__ == "__main__":
    unittest.main()

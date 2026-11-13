"""Regression test for the opacity-to-alpha bar background mixin."""

import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
STYLES = os.path.join(ROOT, "styles")


class BarBackgroundTest(unittest.TestCase):
    """Bar/dock background alpha must follow the configured opacity percentage."""
    def _compile(self, opacity):
        if shutil.which("sass") is None:
            self.skipTest("sass binary not available")

        source = (
            '@use "common/mixins" as mixins;\n'
            f".probe {{ @include mixins.bar-background({opacity}); }}\n"
        )
        with tempfile.NamedTemporaryFile(
            "w", dir=STYLES, suffix=".scss", delete=False
        ) as handle:
            handle.write(source)
            path = handle.name
        try:
            result = subprocess.run(
                ["sass", path, "--no-source-map"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        finally:
            os.unlink(path)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_opacity_percentage_maps_to_alpha(self):
        self.assertIn("rgba(36, 35, 35, 0.9)", self._compile(90))
        self.assertIn("rgba(36, 35, 35, 0.1)", self._compile(10))

    def test_alpha_is_clamped(self):
        # Alpha 1 compresses to the opaque hex colour.
        self.assertIn("#242323", self._compile(150))
        self.assertIn("rgba(36, 35, 35, 0)", self._compile(-10))


if __name__ == "__main__":
    unittest.main()

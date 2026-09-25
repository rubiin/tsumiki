from fabric.core.service import Signal
from fabric.utils import (
    exec_shell_command_async,
    get_relative_path,
    logger,
    os,
)

import utils.functions as helpers
from utils.config import tsumiki_config

from .base import SingletonService

# Config path constant
_CONFIG_PATH = get_relative_path("../assets/matugen/config.toml")


class MatugenService(SingletonService):
    """Service to generate Material You color schemes using Matugen."""

    @Signal
    def colors_generated(self) -> None:
        """Signal emitted when colors are successfully generated."""

    @Signal
    def generation_failed(self, error: str) -> None:
        """Signal emitted when color generation fails."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        helpers.check_executable_exists("matugen")
        self._style_config = tsumiki_config.get("styling", {}).get("matugen", {})
        self._mode = self._style_config.get("mode", "dark")

    def _build_cmd(self, image_path: str) -> list[str]:
        """Build the matugen argv from config.

        A list rather than a shell string, so a wallpaper path needs no
        quoting and cannot be re-parsed.
        """
        scheme = self._style_config.get("scheme", "scheme-tonal-spot")
        contrast = self._style_config.get("contrast", 0.0)

        return [
            "matugen",
            "image",
            "-q",
            image_path,
            "-t",
            scheme,
            "--mode",
            self._mode,
            "--contrast",
            str(contrast),
            "--config",
            _CONFIG_PATH,
            "--source-color-index",
            "0",
        ]

    def generate(self, image_path: str | None = None) -> None:
        """Generate colors from an image asynchronously."""
        image_path = image_path or os.path.expanduser(
            self._style_config.get("wallpaper", "")
        )

        if not os.path.exists(image_path):
            self.emit("generation_failed", f"Image not found: {image_path}")
            return

        cmd = self._build_cmd(image_path)
        logger.info("[Matugen] Generating colors")

        def on_complete(result):
            if result is not None:
                logger.info("[Matugen] Colors generated successfully")
                self.emit("colors_generated")
            else:
                self.emit("generation_failed", "Matugen returned no result")

        exec_shell_command_async(cmd, on_complete)

    def generate_sync(self, image_path: str | None = None) -> bool:
        """Generate colors from an image synchronously."""
        image_path = image_path or os.path.expanduser(
            self._style_config.get("wallpaper", "")
        )

        if not os.path.exists(image_path):
            self.emit("generation_failed", f"Image not found: {image_path}")
            return False

        cmd = self._build_cmd(image_path)
        logger.info("[Matugen] Generating colors")

        try:
            if helpers.run_command(cmd) is None:
                self.emit("generation_failed", "matugen exited non-zero")
                return False
            logger.info("[Matugen] Colors generated successfully")
            self.emit("colors_generated")
            return True
        except Exception as e:
            logger.exception(f"[Matugen] Color generation failed: {e}")
            self.emit("generation_failed", str(e))
            return False

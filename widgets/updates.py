import json
from datetime import datetime

from fabric.utils import (
    cooldown,
    exec_shell_command_async,
    invoke_repeater,
    logger,
)

from shared.widget_container import ButtonWidget
from utils.colors import Colors
from utils.constants import ASSETS_DIR


class UpdatesWidget(ButtonWidget):
    """A widget to display the number of available updates."""

    def __init__(
        self,
        **kwargs,
    ):
        # Initialize the EventBox with specific name and style
        super().__init__(name="updates", **kwargs)

        self.update_time = datetime.now()

        self.base_command = self._build_base_command()

        self.label_format = self.config.get("label_format", "{icon} {total}")
        self.add_formatted_label(
            self.label_format,
            self.config.get("no_updates_icon", "󰒒"),
            total=self._format_total(0),
        )

        self.connect("button-press-event", self.on_click)

        # Set up a repeater to call the update method at specified intervals
        self._check_update()

        # reusing the fabricator to call specified intervals
        self._register_repeater(invoke_repeater(1000, self._should_update))

    def _build_base_command(self) -> str:
        script = f"{ASSETS_DIR}/scripts/systemupdates.sh"
        command = [f"{script} os={self.config.get('os', 'linux')}"]

        # Add terminal option
        command.append(f"--terminal={self.config.get('terminal', 'kitty')}")

        command.extend(
            [
                f"--{opt}"
                for opt in ("flatpak", "snap", "brew")
                if self.config.get(opt, False)
            ]
        )
        return " ".join(command)

    def _should_update(self, *_):
        """Trigger an update when the configured interval has elapsed."""
        if (datetime.now() - self.update_time).total_seconds() >= self.config.get(
            "interval", 3600
        ):
            self._check_update()
            self.update_time = datetime.now()
        return True

    def _format_total(self, total: int) -> str:
        """Render *total* for the ``{total}`` field, honouring ``pad_zero``.

        Zero stays a bare ``0`` so an idle bar does not show a padded count.
        """
        if total == 0 or not self.config.get("pad_zero", True):
            return str(total)
        return str(total).rjust(2, "0")

    def _update_values(self, value: str):
        """Update the UI based on the returned update data."""
        try:
            data = json.loads(value)
            total = int(data.get("total", "0"))

            icon = (
                self.config.get("available_icon", "󰏗")
                if total > 0
                else self.config.get("no_updates_icon", "󰒒")
            )
            self.refresh_formatted_label(icon, total=self._format_total(total))

            # Tooltip
            self.set_tooltip_if_enabled(data.get("tooltip", ""), default=True)

            # Auto-hide logic
            if self.config.get("auto_hide", False) and self.is_visible():
                self.set_visible(False)

        except (json.JSONDecodeError, ValueError) as e:
            logger.exception(
                f"{Colors.ERROR}[UpdatesWidget] Failed to parse update data: {e}"
            )

    def on_click(self, _, event):
        """Trigger a manual update check on click."""
        self._check_update(update=(event.button == 1))
        return True

    @cooldown(1)
    def _check_update(self, update=False):
        """Run the update check asynchronously."""
        suffix = " up" if update else ""
        log_msg = (
            "Updating available updates..." if update else "Checking for updates..."
        )
        logger.info(f"{Colors.INFO}[Updates] {log_msg}")

        exec_shell_command_async(
            f"{self.base_command}{suffix}",
            self._update_values,
        )

        return True

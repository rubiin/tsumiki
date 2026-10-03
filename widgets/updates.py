import json
from datetime import datetime

from fabric.utils import (
    cooldown,
    exec_shell_command_async,
    invoke_repeater,
    logger,
)
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer

from shared.widget_container import ButtonWidget
from utils.colors import Colors
from utils.constants import ASSETS_DIR
from utils.widget_utils import (
    nerd_font_icon,
)


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

        if self.format_shows_icon():
            self.icon = nerd_font_icon(
                icon=self.config.get("no_updates_icon", "󰒲"),
                props={"style_classes": ["panel-font-icon"]},
            )
            self.container_box.add(self.icon)

        if self.config.get("label", True):
            self.update_label = Label(label="0", style_classes="panel-text")

            if self.config.get("hover_reveal", True):
                self.revealer = Revealer(
                    child=self.update_label,
                    transition_duration=self.config.get("reveal_duration", 500),
                    transition_type="slide_right",
                )
                self.container_box.add(self.revealer)
            else:
                self.container_box.add(self.update_label)

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

    def _update_values(self, value: str):
        """Update the UI based on the returned update data."""
        try:
            data = json.loads(value)
            total = int(data.get("total", "0"))

            # Update label
            if self.config.get("label", True):
                label_text = (
                    str(total).rjust(2, "0")
                    if self.config.get("pad_zero", True)
                    else str(total)
                )

                # dont show '0' if total is 0 and pad_zero is True
                if total == 0:
                    label_text = str(total)

                self.update_label.set_label(label_text)

            # Update icon
            if self.format_shows_icon():
                icon = (
                    self.config.get("available_icon")
                    if total > 0
                    else self.config.get("no_updates_icon", "󰒲")
                )
                self.icon.set_label(icon)

            # Tooltip
            self.set_tooltip_if_enabled(data.get("tooltip", ""), default=True)

            # Auto-hide logic
            if self.config.get("auto_hide", False):
                self.set_visible(total > 0)

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

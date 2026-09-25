from typing import ClassVar

from fabric.utils import GObject, logger

from utils.hyprland import hyprland_service
from utils.icons import symbolic_icons

from ..osd import GenericOSDContainer


class LockkeysOSDContainer(GenericOSDContainer):
    """OSD for capslock/numlock state, driven by Hyprland activelayout events."""

    __gsignals__: ClassVar = {
        "locks-changed": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self, config: dict, **kwargs):
        super().__init__(
            config=config,
            **kwargs,
        )
        self.config = config
        self.previous_capslock = None
        self.previous_numlock = None

        # Create text display for locks
        from fabric.widgets.label import Label

        self.lock_label = Label(
            label="",
            style_classes="osd-lock-label",
            name="lock-label",
        )

        # Replace scale with lock display
        self.children = (self.icon, self.lock_label)

        # Subscribe to Hyprland event — fires on keyboard layout changes.
        # Tracked by TeardownMixin, which the OSD base already wires to
        # "destroy", so this needs no cleanup() of its own.
        self._register_handlers(
            hyprland_service,
            {"event::activelayout": self._on_activelayout},
        )

        # Initial query
        self._query_lock_state()

    def _on_activelayout(self, *_):
        """Hyprland layout-change event — query lock state."""
        self._query_lock_state()

    def _query_lock_state(self) -> bool:
        """Query current lock state via Hyprland socket (async)."""
        hyprland_service.get_devices_async(self._on_devices_data)
        return True

    def _on_devices_data(self, data, *_):
        """Parse j/devices reply for capslock/numlock."""
        if data is None:
            return
        try:
            keyboards = data.get("keyboards", [])
            main_kb = next((kb for kb in keyboards if kb.get("main")), None)
            if main_kb is None:
                return

            caps = main_kb.get("capsLock", False)
            num = main_kb.get("numLock", False)

            if self.previous_capslock != caps or self.previous_numlock != num:
                self.previous_capslock = caps
                self.previous_numlock = num

                self._update_display(caps, num)
                self.emit("locks-changed")

        except (KeyError, TypeError, AttributeError) as e:
            logger.warning(f"[LockkeysOSD] Parse error: {e}")

    def _update_display(self, caps: bool, num: bool):
        """Update icon and label based on lock state."""
        # Update icon
        if caps or num:
            icon_name = symbolic_icons.get("keyboard", {}).get(
                "locks", "input-keyboard-symbolic"
            )
        else:
            icon_name = "input-keyboard-symbolic"

        self.icon.set_from_icon_name(icon_name, self.icon_size)

        # Update label
        status_parts = []
        if caps:
            status_parts.append("⇪ CAPS")
        if num:
            status_parts.append("🔢 NUM")

        label_text = " | ".join(status_parts) if status_parts else "No locks"
        self.lock_label.set_label(label_text)

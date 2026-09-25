import json
import shlex
from functools import partial

from fabric.utils import (
    GLib,
    Gtk,
    exec_shell_command_async,
    logger,
)
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label

from shared.buttons import HoverButton, ScanButton
from shared.list import ListBox
from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget, TeardownMixin
from utils.i18n import _
from utils.widget_utils import nerd_font_icon


class USBManagerMenu(Box, TeardownMixin):
    """Popover content for managing removable USB drives."""

    def __init__(self, parent=None, config=None, **kwargs):
        super().__init__(
            name="usb-manager-menu",
            orientation="v",
            spacing=8,
            h_expand=True,
            **kwargs,
        )

        self._parent = parent
        self.config = config or {}
        self.devices = []
        self._refresh_timer_id: int | None = None
        self._lsblk_lines: list[str] = []
        self._lsblk_finalize_id: int | None = None

        self.title = Label(
            label=_("widget.usb_manager.title"),
            h_align="start",
            name="usb-manager-title",
            style_classes="panel-text",
        )

        self.title_icon = nerd_font_icon(
            icon="󰕓",
            props={"style_classes": ["panel-font-icon", "title-icon"]},
        )

        self.refresh_button = ScanButton(
            on_clicked=self._on_refresh_clicked,
            sensitive=False,
            tooltip_text=_("common.refresh"),
            size=17,
        )

        header = CenterBox(
            name="usb-manager-header",
            orientation="h",
            h_expand=True,
            start_children=[self.title_icon, self.title],
            end_children=[self.refresh_button],
        )

        self.device_list = ListBox(
            name="usb-manager-list",
            h_expand=True,
            v_expand=True,
        )

        self.content = Box(
            name="usb-manager-content",
            orientation="v",
            h_expand=True,
            v_expand=True,
        )

        self.unmount_all_button = HoverButton(
            name="usb-manager-unmount-all",
            style_classes="usb-manager-btn",
            child=self._build_button_content(
                icon="󱘖",
                label=_("widget.usb_manager.unmount_all"),
            ),
            on_clicked=self.unmount_all,
        )
        self.eject_all_button = HoverButton(
            name="usb-manager-eject-all",
            style_classes="usb-manager-btn",
            child=self._build_button_content(
                icon="⏏",
                label=_("widget.usb_manager.eject_all"),
            ),
            on_clicked=self.eject_all,
        )

        footer = CenterBox(
            name="usb-manager-footer",
            orientation="h",
            spacing=8,
            start_children=[self.unmount_all_button],
            end_children=[self.eject_all_button],
        )

        self.children = [header, self.content, footer]

        self.connect("destroy", self._on_destroy)
        self.refresh_devices()

    # Invoked from _on_action_done — timer cleanup is handled by TeardownMixin

    def _update_footer_buttons(self):
        mounted_count = sum(1 for device in self.devices if device.get("mountpoint"))
        parent_paths = {
            device.get("parent_path")
            for device in self.devices
            if device.get("parent_path")
        }
        has_devices = bool(self.devices)

        self.unmount_all_button.set_visible(has_devices)
        self.eject_all_button.set_visible(has_devices)
        self.unmount_all_button.set_sensitive(has_devices and mounted_count > 0)
        self.eject_all_button.set_sensitive(has_devices and bool(parent_paths))

    def _on_refresh_clicked(self, *_):
        self.refresh_devices(animate=True)

    def _on_destroy(self, *_):
        self._refresh_timer_id = None
        if self._lsblk_finalize_id is not None:
            self._unregister_repeater(self._lsblk_finalize_id)
            GLib.source_remove(self._lsblk_finalize_id)
            self._lsblk_finalize_id = None
        return None

    def close(self, *_):
        if self._parent:
            self._parent.hide_popover()

    def _is_usb_disk(self, node: dict) -> bool:
        return node.get("type") == "disk" and (
            str(node.get("tran", "")).lower() == "usb"
            or bool(node.get("rm"))
            or bool(node.get("hotplug"))
        )

    @staticmethod
    def _is_mountable(node: dict) -> bool:
        return bool(node.get("path")) and bool(node.get("fstype"))

    def _collect_usb_partitions(self, blockdevices: list[dict]) -> list[dict]:
        devices: list[dict] = []

        def walk(node: dict, parent_usb_disk: dict | None = None):
            active_parent = parent_usb_disk
            if self._is_usb_disk(node):
                active_parent = node

            if active_parent and self._is_mountable(node):
                devices.append(
                    {
                        "name": node.get("name", "unknown"),
                        "path": node.get("path", ""),
                        "size": node.get("size", "?"),
                        "fstype": str(node.get("fstype", "")).upper(),
                        "label": node.get("label") or "",
                        "mountpoint": node.get("mountpoint") or "",
                        "fsuse_pct": node.get("fsuse%") or "",
                        "fsused": node.get("fsused") or "",
                        "fsavail": node.get("fsavail") or "",
                        "parent_path": active_parent.get("path", node.get("path", "")),
                        "parent_name": active_parent.get("name", node.get("name", "")),
                    }
                )

            for child in node.get("children", []) or []:
                walk(child, active_parent)

        for entry in blockdevices:
            walk(entry, None)

        return devices

    def refresh_devices(self, *_, animate: bool = False):
        if animate:
            self.refresh_button.play_animation()

        self._lsblk_lines = []
        if self._lsblk_finalize_id is not None:
            self._unregister_repeater(self._lsblk_finalize_id)
            GLib.source_remove(self._lsblk_finalize_id)
            self._lsblk_finalize_id = None

        exec_shell_command_async(
            "lsblk  --output NAME,PATH,TYPE,SIZE,FSTYPE,"
            "LABEL,MOUNTPOINT,FSUSE%,FSUSED,FSAVAIL,RM,HOTPLUG,TRAN --json",
            self._on_lsblk_line,
        )

    def _on_lsblk_line(self, line: str):
        """Accumulate lsblk output lines; finalize ~200ms after last line."""
        self._lsblk_lines.append(line)
        if self._lsblk_finalize_id is not None:
            self._unregister_repeater(self._lsblk_finalize_id)
            GLib.source_remove(self._lsblk_finalize_id)
        self._lsblk_finalize_id = self._register_repeater(
            GLib.timeout_add(200, self._finalize_lsblk)
        )

    def _finalize_lsblk(self):
        """Parse the accumulated lsblk output and update the device list."""
        self._lsblk_finalize_id = None
        output = "\n".join(self._lsblk_lines)
        self._lsblk_lines = []

        parsed = self._parse_lsblk_output(output)

        if parsed is None:
            self.devices = []
            self._render_devices(error_message="USB scan unavailable")
            self._update_footer_buttons()
            if self._parent:
                self._parent.update_device_count(0)
            return

        blockdevices = parsed.get("blockdevices", [])
        self.devices = self._collect_usb_partitions(blockdevices)

        self._render_devices()
        self._update_footer_buttons()
        if self._parent:
            self._parent.update_device_count(len(self.devices))
        return False

    @staticmethod
    def _parse_lsblk_output(output: str) -> dict | None:
        text = (output or "").strip()

        if not text:
            return None

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as err:
            logger.warning(f"[USBManager] lsblk output not JSON: {err}")
            return None

        if not isinstance(parsed, dict):
            return None
        return parsed

    def _render_devices(self, error_message: str | None = None):
        if error_message:
            self.devices = []
            self._set_content(
                self._build_status_view(
                    title=error_message,
                    subtitle="Check lsblk permissions and try refresh",
                    icon="",
                )
            )
            self._update_footer_buttons()
            return

        if not self.devices:
            self._set_content(
                self._build_status_view(
                    title=_("widget.usb_manager.no_devices"),
                    subtitle=_("widget.usb_manager.plug_in"),
                    icon="󰕓",
                )
            )
            self._update_footer_buttons()
            return

        self.device_list.remove_all()
        for device in self.devices:
            self.device_list.add(self._build_device_row(device))

        self._set_content(self.device_list)
        self._update_footer_buttons()

    def _set_content(self, child: Box | Gtk.ListBox):
        for existing in self.content.get_children():
            self.content.remove(existing)
        self.content.add(child)

    def _build_status_view(self, title: str, subtitle: str, icon: str) -> Box:
        icon_widget = nerd_font_icon(
            icon=icon,
            props={"style_classes": ["panel-font-icon", "usb-manager-status-icon"]},
        )

        title_label = Label(
            label=title,
            h_align="center",
            style_classes=["panel-text", "usb-manager-status-title"],
        )

        subtitle_label = Label(
            label=subtitle,
            h_align="center",
            style_classes=["panel-text", "usb-manager-status-subtitle"],
        )

        return Box(
            name="usb-manager-status-view",
            orientation="v",
            spacing=8,
            h_align="center",
            v_align="center",
            h_expand=True,
            v_expand=True,
            children=[icon_widget, title_label, subtitle_label],
        )

    def _build_device_row(self, device: dict) -> Box:
        mounted = bool(device.get("mountpoint"))
        primary_label = (
            _("widget.usb_manager.open") if mounted else _("widget.usb_manager.mount")
        )
        usage_text = self._build_usage_text(device)
        usage_fraction = self._usage_fraction(device)

        title = Label(
            label=device.get("label", "unknown"),
            h_align="start",
            name="usb-manager-device-name",
            style_classes=["panel-text", "usb-manager-device-name"],
        )

        details_parts = [device.get("size", "?"), device.get("fstype", "")]

        details = Label(
            label=" • ".join([part for part in details_parts if part]),
            h_align="start",
            style_classes=["panel-text", "usb-manager-device-meta"],
        )

        mountpoint_label = Label(
            label=device.get("mountpoint") or "",
            h_align="start",
            style_classes=["panel-text", "usb-manager-device-path"],
        )

        usage_label = Label(
            label=usage_text,
            h_align="start",
            visible=bool(usage_text),
            style_classes=["panel-text", "usb-manager-device-usage"],
        )

        usage_progress = Gtk.ProgressBar(
            name="usb-manager-usage-progress",
            fraction=usage_fraction or 0.0,
            visible=usage_fraction is not None,
            hexpand=True,
            vexpand=False,
            show_text=False,
        )

        icon = nerd_font_icon(
            icon="󰕓",
            props={"style_classes": ["panel-font-icon"]},
        )

        status_badge = Label(
            label=(
                _("widget.usb_manager.mounted")
                if mounted
                else _("widget.usb_manager.ready")
            ),
            style_classes=["panel-text", "usb-manager-status-badge"],
            visible=mounted,
        )

        title_row = Box(
            name="usb-manager-item-header",
            orientation="h",
            spacing=6,
            h_expand=True,
            children=[icon, title],
        )

        header = CenterBox(
            name="usb-manager-device-header",
            orientation="h",
            h_expand=True,
            start_children=[title_row],
            end_children=[status_badge],
        )

        primary_button = HoverButton(
            name="usb-manager-action-primary",
            style_classes=["usb-manager-btn", "usb-manager-primary-btn"],
            h_expand=True,
            child=self._build_button_content(
                icon="" if mounted else "",
                label=primary_label,
            ),
            on_clicked=(
                partial(self.open_device, device)
                if mounted
                else partial(self.mount_device, device)
            ),
        )

        secondary_button = HoverButton(
            name="usb-manager-action-secondary",
            style_classes=["usb-manager-btn", "usb-manager-icon-btn"],
            visible=mounted,
            child=nerd_font_icon(
                icon="󱘖",
                props={"style_classes": ["panel-font-icon"]},
            ),
            tooltip_text=_("widget.usb_manager.unmount"),
            on_clicked=partial(self.unmount_device, device),
        )

        eject_button = HoverButton(
            name="usb-manager-action-eject",
            style_classes=["usb-manager-btn", "usb-manager-icon-btn"],
            child=nerd_font_icon(
                icon="⏏",
                props={"style_classes": ["panel-font-icon"]},
            ),
            tooltip_text=_("widget.usb_manager.eject"),
            on_clicked=partial(self.eject_device, device),
        )

        actions = Box(
            name="usb-manager-device-actions",
            orientation="h",
            spacing=6,
            h_expand=True,
            children=[primary_button, secondary_button, eject_button],
        )

        row_children = [
            header,
            details,
            mountpoint_label,
            usage_progress,
            usage_label,
            actions,
        ]

        return Box(
            name="usb-manager-item",
            orientation="v",
            spacing=3,
            children=row_children,
        )

    @staticmethod
    def _build_usage_text(device: dict) -> str:
        used = str(device.get("fsused") or "").strip()
        free = str(device.get("fsavail") or "").strip()
        if used and free:
            return f"{used} used           {free} free"
        if used:
            return f"{used} used"
        if free:
            return f"{free} free"
        return ""

    @staticmethod
    def _usage_fraction(device: dict) -> float | None:
        raw_pct = str(device.get("fsuse_pct") or "").strip().rstrip("%")
        if not raw_pct:
            return None

        try:
            pct = float(raw_pct)
        except ValueError:
            return None

        if pct < 0:
            pct = 0
        if pct > 100:
            pct = 100
        return pct / 100.0

    @staticmethod
    def _build_button_content(icon: str, label: str) -> Box:
        return Box(
            orientation="h",
            spacing=5,
            h_align="center",
            children=[
                nerd_font_icon(
                    icon=icon,
                    props={"style_classes": ["panel-font-icon", "btn-icon"]},
                ),
                Label(label=label, style_classes="panel-text"),
            ],
        )

    def _run_command(self, command: str):
        def on_command_done(*_):
            self._on_action_done()

        exec_shell_command_async(command, on_command_done)

    def _on_action_done(self, *_):
        if self._refresh_timer_id is not None:
            self._unregister_repeater(self._refresh_timer_id)
            GLib.source_remove(self._refresh_timer_id)
        self._refresh_timer_id = self._register_repeater(
            GLib.timeout_add(250, self._refresh_after_action)
        )

    def _refresh_after_action(self):
        self.refresh_devices()
        return False

    def mount_device(self, device: dict, *_):
        path = device.get("path")
        if path:
            self._run_command(f"udisksctl mount -b {shlex.quote(path)}")

    def open_device(self, device: dict, *_):
        mountpoint = device.get("mountpoint")
        if mountpoint:
            self._run_command(f"xdg-open {shlex.quote(mountpoint)}")

    def unmount_device(self, device: dict, *_):
        path = device.get("path")
        if path:
            self._run_command(f"udisksctl unmount -b {shlex.quote(path)}")

    def eject_device(self, device: dict, *_):
        path = device.get("parent_path") or device.get("path")
        if path:
            self._run_command(f"udisksctl power-off -b {shlex.quote(path)}")

    def unmount_all(self, *_):
        mounted_paths = [
            shlex.quote(device["path"])
            for device in self.devices
            if device.get("mountpoint") and device.get("path")
        ]
        if not mounted_paths:
            return

        command = " && ".join(
            [f"udisksctl unmount -b {path}" for path in mounted_paths]
        )
        self._run_command(command)

    def eject_all(self, *_):
        parent_paths = {
            shlex.quote(device["parent_path"])
            for device in self.devices
            if device.get("parent_path")
        }
        if not parent_paths:
            return

        command = " && ".join(
            [f"udisksctl power-off -b {path}" for path in sorted(parent_paths)]
        )
        self._run_command(command)


class USBManagerWidget(ButtonWidget, PopoverMixin):
    """A panel widget for mounting and ejecting USB drives."""

    def __init__(self, **kwargs):
        super().__init__(name="usb_manager", **kwargs)

        self.add_panel_content(
            self.config.get("icon", ""),
            _("widget.usb_manager.label"),
            show_label=self.config.get("label", False),
        )

        self.set_tooltip_if_enabled(_("widget.usb_manager.tooltip"), default=True)

        self.setup_popover(self._build_popover)

    def _build_popover(self):
        return USBManagerMenu(parent=self, config=self.config)

    def show_popover(self, *_):
        super().show_popover()
        if self.popup:
            self.popup.content.refresh_devices()

    def update_device_count(self, count: int):
        self.set_tooltip_if_enabled(_("widget.usb_manager.tooltip"), default=True)

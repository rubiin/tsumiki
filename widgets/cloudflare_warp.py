from fabric.utils import GLib
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from services.cloudflare_warp import cloudflare_warp_service
from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget
from utils.exceptions import ExecutableNotFoundError
from utils.functions import check_executable_exists
from utils.i18n import _
from utils.widget_utils import nerd_font_icon


class CloudflareWarpPopover(Box):
    """Popover content with WARP connection controls and status details."""

    def __init__(self, parent=None, **kwargs):
        super().__init__(
            name="cloudflare-warp-popover",
            orientation="v",
            spacing=12,
            **kwargs,
        )

        self._parent = parent
        self._service = cloudflare_warp_service

        # ── Status indicator ──
        self._status_icon = nerd_font_icon(
            icon="",
            props={"style_classes": ["warp-status-icon"]},
        )

        self._status_label = Label(
            name="warp-status-label",
            label=_("common.loading"),
            h_align="center",
        )

        status_box = Box(
            name="warp-status-box",
            orientation="v",
            spacing=6,
            h_align="center",
            children=[self._status_icon, self._status_label],
        )

        # ── Toggle button ──
        self._toggle_btn = Button(
            name="warp-toggle-btn",
            label=_("widget.cloudflare_warp.connect"),
            h_align="center",
            on_clicked=lambda *_: self._on_toggle(),
        )

        # ── Layout ──
        self.children = [status_box, self._toggle_btn]

        self._destroyed = False
        self._re_enable_timer_id = None
        self._handler_id = self._service.connect("changed", self._on_status_changed)
        self.connect("destroy", self._on_destroy)

        self._on_status_changed()

    def _on_status_changed(self, *_args):
        connected = self._service.connected

        if connected:
            self._status_icon.set_label("")
            self._status_icon.set_style_classes(["warp-status-icon", "warp-connected"])
            self._status_label.set_label(_("widget.cloudflare_warp.connected"))
            self._toggle_btn.set_label(_("widget.cloudflare_warp.disconnect"))
        else:
            self._status_icon.set_label("")
            self._status_icon.set_style_classes(
                ["warp-status-icon", "warp-disconnected"]
            )
            self._status_label.set_label(_("widget.cloudflare_warp.disconnected"))
            self._toggle_btn.set_label(_("widget.cloudflare_warp.connect"))

        self._toggle_btn.set_sensitive(True)

    def _on_toggle(self):
        self._toggle_btn.set_sensitive(False)
        self._service.toggle_warp()
        # Re-enable after a short delay
        self._re_enable_timer_id = GLib.timeout_add(
            2000, lambda: self._re_enable_btn() or False
        )

    def _re_enable_btn(self):
        if not self._destroyed:
            self._toggle_btn.set_sensitive(True)

    def _on_destroy(self, *_):
        self._destroyed = True
        self._service.pause_polling()
        if self._re_enable_timer_id is not None:
            GLib.source_remove(self._re_enable_timer_id)
            self._re_enable_timer_id = None
        if self._handler_id:
            self._service.disconnect(self._handler_id)
            self._handler_id = None

    def close(self, *_):
        if self._parent:
            self._parent.hide_popover()


class CloudflareWarpWidget(ButtonWidget, PopoverMixin):
    """Bar widget showing Cloudflare WARP connection status."""

    def __init__(self, **kwargs):
        super().__init__(name="cloudflare_warp", **kwargs)

        self._service = cloudflare_warp_service
        self._available = True

        self._connected_icon = self.config.get("connected_icon", "")
        self._disconnected_icon = self.config.get("disconnected_icon", "")

        # Check if warp-cli is installed
        try:
            check_executable_exists("warp-cli")
        except ExecutableNotFoundError:
            self._available = False
            self._connected_icon = ""
            self._disconnected_icon = ""

        if self._available:
            self._icon = nerd_font_icon(
                icon=self._connected_icon,
                props={"style_classes": ["panel-font-icon"]},
            )
            self.set_tooltip_text(_("widget.cloudflare_warp.tooltip"))
            self._register_handlers(
                self._service,
                {"changed": self._on_status_changed},
            )
            # Pause background polling when widget is hidden, resume when shown
            self.connect("map", lambda *_: self._service.resume_polling())
            self.connect("unmap", lambda *_: self._service.pause_polling())
        else:
            self._icon = nerd_font_icon(
                icon="",
                props={"style_classes": ["panel-font-icon"]},
            )
            self.set_tooltip_text(_("widget.cloudflare_warp.not_found"))

        self.container_box.add(self._icon)

        if self.config.get("label", False):
            self.container_box.add(
                Label(
                    label=self.config.get("label_text", "WARP"),
                    style_classes="panel-text",
                )
            )

        if self._available:
            self.setup_popover(lambda: CloudflareWarpPopover(parent=self))

    def _on_status_changed(self, *_args):
        if not self._available:
            return
        if self._service.connected:
            self._icon.set_label(self._connected_icon)
            self.set_tooltip_text(_("widget.cloudflare_warp.status_connected"))
        else:
            self._icon.set_label(self._disconnected_icon)
            self.set_tooltip_text(_("widget.cloudflare_warp.status_disconnected"))

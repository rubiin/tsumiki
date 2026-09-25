from fabric.utils import Gtk
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

from services.dns_switcher import DEFAULT_PROVIDERS, dns_switcher_service
from shared.list import ListBox
from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget
from utils.i18n import _
from utils.widget_utils import nerd_font_icon


class DnsSwitcherPopover(Box):
    """Popover content matching Noctalia DNS Switcher UI."""

    def __init__(self, parent=None, **kwargs):
        super().__init__(
            name="dns-switcher-popover",
            orientation="v",
            spacing=8,
            **kwargs,
        )

        self._parent = parent
        self._service = dns_switcher_service
        self._is_adding = False

        # ── Header ──
        self._header_status = Label(
            name="dns-header-status",
            label="...",
            h_align="end",
            v_align="center",
        )

        header = Box(
            name="dns-header",
            orientation="h",
            spacing=8,
            children=[
                nerd_font_icon(
                    icon="󰚘",
                    props={"style_classes": ["dns-header-icon"]},
                ),
                Label(
                    name="dns-header-title",
                    label=_("widget.dns_switcher.tooltip"),
                    h_align="start",
                    v_align="center",
                    h_expand=True,
                ),
                self._header_status,
            ],
        )

        # ── Provider list ──
        self._provider_list = ListBox(
            name="dns-provider-list",
            visible=True,
        )
        self._provider_rows: list[Gtk.ListBoxRow] = []
        self._rebuild_provider_list()

        scroll = ScrolledWindow(
            name="dns-scroll",
            min_content_size=(300, 150),
            max_content_size=(320, 280),
            child=self._provider_list,
        )

        # ── Add Custom Server button ──
        self._add_btn_box = Box(
            spacing=6,
            children=[
                nerd_font_icon(
                    icon="",
                    props={"style_classes": ["dns-btn-icon"]},
                ),
                Label(label=_("widget.dns_switcher.add_custom")),
            ],
        )
        # Keep a reference to the label so we can change text later
        self._add_btn_label = self._add_btn_box.children[1]
        self._add_btn = Button(
            name="dns-add-btn",
            child=self._add_btn_box,
            on_clicked=lambda *_: self._toggle_add_section(),
        )

        # ── Add Custom Server form ──
        self._name_entry = Entry(
            name="dns-custom-name",
            placeholder="Name (e.g. My DNS)",
            h_expand=True,
        )
        self._ip_entry = Entry(
            name="dns-custom-ip",
            placeholder="IP Address (e.g. 1.2.3.4 5.6.7.8)",
            h_expand=True,
        )
        self._save_btn = Button(
            name="dns-save-btn",
            label=_("common.save"),
            on_clicked=lambda *_: self._on_save_custom(),
        )

        self._add_form = Box(
            name="dns-add-form",
            orientation="v",
            spacing=6,
            visible=False,
            children=[
                Box(
                    spacing=6,
                    children=[self._name_entry, self._ip_entry],
                ),
                self._save_btn,
            ],
        )

        # ── Reset button ──
        self._reset_btn = Button(
            name="dns-reset-btn",
            child=Box(
                spacing=6,
                children=[
                    nerd_font_icon(
                        icon="",
                        props={"style_classes": ["dns-btn-icon"]},
                    ),
                    Label(label=_("widget.dns_switcher.reset")),
                ],
            ),
            on_clicked=lambda *_: self._on_reset(),
        )

        # ── Layout ──
        self.children = [
            header,
            scroll,
            self._add_btn,
            self._add_form,
            self._reset_btn,
        ]

        self._handler_id = self._service.connect(
            "notify::current", self._on_current_changed
        )
        self.connect("destroy", self._on_destroy)
        self._service.resume_polling()

        self._on_current_changed()

    def _rebuild_provider_list(self):
        self._provider_list.remove_all()
        self._provider_rows.clear()

        for idx, prov in enumerate(DEFAULT_PROVIDERS):

            def make_cb(i):
                return lambda *_: self._on_select_provider(i)

            radio = nerd_font_icon(
                icon="",
                props={"style_classes": ["dns-radio-icon"]},
            )

            row_content = Button(
                name="dns-provider-btn",
                child=Box(
                    spacing=10,
                    children=[
                        radio,
                        Label(
                            label=prov["label"],
                            h_align="start",
                            v_align="center",
                            h_expand=True,
                            style_classes="dns-provider-label",
                        ),
                        Label(
                            label=f"{prov['primary']}",
                            h_align="end",
                            v_align="center",
                            style_classes="dns-provider-ip",
                        ),
                    ],
                ),
                on_clicked=make_cb(idx),
            )

            row = Gtk.ListBoxRow(
                name="dns-provider-row",
                visible=True,
                activatable=True,
            )
            row.add(row_content)
            row._radio = radio
            row._provider_id = prov["label"]
            self._provider_list.add(row)
            self._provider_rows.append(row)

    def _on_select_provider(self, index: int):
        self._service.switch_provider(index)
        self._update_active_state()

    def _update_active_state(self):
        current = self._service.current
        for row in self._provider_rows:
            btn = row.get_child()
            is_active = row._provider_id == current
            if is_active:
                btn.set_style_classes(["dns-provider-btn-active"])
                row._radio.set_label("")
            else:
                btn.set_style_classes(["dns-provider-btn"])
                row._radio.set_label("○")

    def _on_current_changed(self, *_args):
        current = self._service.current
        self._update_active_state()
        if current and current != "Default":
            self._header_status.set_label(current)
            self._header_status.set_style_classes(["dns-status-active"])
        else:
            self._header_status.set_label(_("widget.dns_switcher.default"))
            self._header_status.set_style_classes(["dns-status-default"])

    def _toggle_add_section(self):
        self._is_adding = not self._is_adding
        self._add_form.set_visible(self._is_adding)
        if self._is_adding:
            self._add_btn_label.set_label(_("common.cancel"))
            self._add_btn.set_style_classes(["dns-cancel-btn"])
        else:
            self._add_btn_label.set_label(_("widget.dns_switcher.add_custom"))
            self._add_btn.set_style_classes([])
            self._name_entry.set_text("")
            self._ip_entry.set_text("")

    def _on_save_custom(self):
        name = self._name_entry.get_text().strip()
        ip = self._ip_entry.get_text().strip()
        if name and ip:
            # For now, just switch to first IP as a custom DNS
            primary = ip.split()[0]
            self._service.set_dns(primary, " ".join(ip.split()[1:]))
            self._is_adding = False
            self._add_form.set_visible(False)
            self._add_btn_label.set_label(_("widget.dns_switcher.add_custom"))
            self._add_btn.set_style_classes([])
            self._name_entry.set_text("")
            self._ip_entry.set_text("")

    def _on_reset(self):
        self._service.reset_to_default()

    def _on_destroy(self, *_):
        self._service.pause_polling()
        if self._handler_id:
            self._service.disconnect(self._handler_id)
            self._handler_id = None

    def close(self, *_):
        if self._parent:
            self._parent.hide_popover()


class DnsSwitcherWidget(ButtonWidget, PopoverMixin):
    """Bar widget showing current DNS provider (icon + dynamic label)."""

    def __init__(self, **kwargs):
        super().__init__(name="dns_switcher", **kwargs)

        self._service = dns_switcher_service

        # ── Icon ──
        self._icon = nerd_font_icon(
            icon=self.config.get("icon", "󰚘"),
            props={"style_classes": ["panel-font-icon"]},
        )
        self.container_box.add(self._icon)

        # ── Dynamic label (like original: shows current provider name) ──
        self._label = Label(
            label=self.config.get("label_text", "DNS"),
            style_classes="panel-text",
        )
        self.container_box.add(self._label)

        self.set_tooltip_if_enabled(_("widget.dns_switcher.tooltip"), default=True)

        self._register_handlers(
            self._service,
            {"notify::current": self._on_current_changed},
        )

        self.setup_popover(lambda: DnsSwitcherPopover(parent=self))

    def _on_current_changed(self, *_args):
        current = self._service.current
        if current and current != "Default":
            self._label.set_label(current)
            self.set_tooltip_text(_("widget.dns_switcher.current", provider=current))
        else:
            self._label.set_label(self.config.get("label_text", "DNS"))
            self.set_tooltip_text(_("widget.dns_switcher.default"))

import json
from collections import defaultdict
from math import ceil

from fabric.utils import logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack

from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget
from utils.hyprland import hyprland_service
from utils.i18n import _

_MODMASK_MAP = {
    64: "SUPER",
    8: "ALT",
    4: "CTRL",
    1: "SHIFT",
}


def _modmask_to_key(modmask: int) -> str:
    keys = [
        key
        for bitfield, key in _MODMASK_MAP.items()
        if (modmask & bitfield) == bitfield
    ]
    known_bits = sum(_MODMASK_MAP.keys())
    unknown_bits = modmask & (~known_bits)
    if unknown_bits != 0:
        keys.append(f"({unknown_bits})")
    return " + ".join(keys)


class CheatSheetMenu(Box):
    """Popover content that renders grouped Hyprland keybinds."""

    def __init__(self, parent=None, config=None, **kwargs):
        super().__init__(
            name="cheatsheet-menu",
            orientation="v",
            spacing=8,
            h_expand=True,
            **kwargs,
        )

        self._parent = parent
        self.config = config or {}

        self.columns = 2
        self.groups_per_page = self.columns * 2
        self.max_entries_per_group = max(
            1, int(self.config.get("max_entries_per_group", 8))
        )
        self.menu_width = 1200
        horizontal_padding = 28
        row_spacing_total = (self.columns - 1) * 8
        self.group_width = max(
            180,
            (self.menu_width - horizontal_padding - row_spacing_total) // self.columns,
        )

        self.groups = self._load_groups()
        self.current_page = 0
        self.total_pages = max(1, ceil(len(self.groups) / self.groups_per_page))

        self.title = Label(
            name="cheatsheet-title",
            style_classes="cheatsheet-title",
            label=self.config.get("title", "Hyprland Cheatsheet"),
            h_align="start",
        )

        self.stack = Stack(
            name="cheatsheet-stack",
            orientation="v",
            transition_type="slide-left-right",
            transition_duration=180,
            h_expand=True,
            v_expand=False,
        )

        self.prev_button = Button(
            name="cheatsheet-nav-btn",
            style_classes="cheatsheet-nav-btn",
            child=Label(
                name="cheatsheet-nav-icon",
                style_classes="cheatsheet-nav-icon",
                label="<",
            ),
            on_clicked=lambda *_: self._change_page(-1),
        )
        self.next_button = Button(
            name="cheatsheet-nav-btn",
            style_classes="cheatsheet-nav-btn",
            child=Label(
                name="cheatsheet-nav-icon",
                style_classes="cheatsheet-nav-icon",
                label=">",
            ),
            on_clicked=lambda *_: self._change_page(1),
        )
        self.page_label = Label(
            name="cheatsheet-page-label",
            style_classes="cheatsheet-page-label",
            label="1/1",
        )

        self.pagination = Box(
            name="cheatsheet-pagination",
            style_classes="cheatsheet-pagination",
            orientation="h",
            spacing=8,
            h_align="center",
            children=[self.prev_button, self.page_label, self.next_button],
        )

        self.children = [self.title, self.stack, self.pagination]

        self._build_pages()

    def _load_groups(self):
        # Start async load of Hyprland binds via the IPC connection
        hyprland_service.send_command_async("binds -j", self._on_binds_reply)

        # Show fallback groups until the async reply comes
        return [
            {
                "title": "Loading…",
                "entries": [
                    {
                        "keys": "N/A",
                        "description": "Loading keybinds from Hyprland…",
                    }
                ],
            }
        ]

    def _on_binds_reply(self, reply, *_):
        """Handle the async binds -j reply."""
        if reply is None:
            logger.debug("[Cheatsheet] Failed to load hyprctl binds")
            return

        try:
            binds = json.loads(reply.reply.decode().strip("\n"))
        except Exception as error:
            logger.debug(f"[Cheatsheet] Failed to parse hyprctl binds: {error}")
            return

        grouped_entries: dict[str, list[dict[str, str]]] = defaultdict(list)

        for bind in binds:
            if not isinstance(bind, dict):
                continue

            modmask = int(bind.get("modmask", 0) or 0)
            key = str(bind.get("key", "")).strip()
            dispatcher = str(bind.get("dispatcher", "")).strip()
            arg = str(bind.get("arg", "")).strip()
            description = str(bind.get("description", "")).strip()

            modifier_keys = _modmask_to_key(modmask)
            keybind = f"{modifier_keys} + {key}".strip(" +") if modifier_keys else key

            if not keybind:
                continue

            if not description:
                description = f"{dispatcher}: {arg}".strip(": ")
            if not description:
                description = dispatcher or "Unlabeled action"

            title = dispatcher.replace("_", " ").strip().title() or "Misc"
            grouped_entries[title].append(
                {
                    "keys": keybind,
                    "description": description,
                }
            )

        self.groups = [
            {
                "title": title,
                "entries": entries,
            }
            for title, entries in sorted(grouped_entries.items())
            if entries
        ]

        # Recalculate page count and rebuild pages with the real data
        self.total_pages = max(1, ceil(len(self.groups) / self.groups_per_page))
        self._build_pages()

    def _build_pages(self):
        self.stack.children = []

        for page_index in range(self.total_pages):
            start = page_index * self.groups_per_page
            end = start + self.groups_per_page
            page_groups = self.groups[start:end]

            page = Box(
                name="cheatsheet-page",
                style_classes="cheatsheet-page",
                orientation="v",
                spacing=8,
            )

            for row_start in range(0, len(page_groups), self.columns):
                row_groups = page_groups[row_start : row_start + self.columns]
                row = Box(
                    name="cheatsheet-row",
                    style_classes="cheatsheet-row",
                    orientation="h",
                    spacing=8,
                    homogeneous=True,
                    h_expand=True,
                )

                for group in row_groups:
                    row.add(self._build_group(group))

                for x in range(self.columns - len(row_groups)):
                    placeholder = Box(
                        name="cheatsheet-group-placeholder",
                        style_classes="cheatsheet-group-placeholder",
                        h_expand=True,
                    )
                    placeholder.set_size_request(self.group_width, -1)
                    row.add(placeholder)

                page.add(row)

            self.stack.add_named(page, f"page-{page_index}")

        self._set_page(0)

    def _build_group(self, group):
        box = Box(
            name="cheatsheet-group",
            style_classes="cheatsheet-group",
            orientation="v",
            spacing=6,
            h_expand=True,
        )
        box.set_size_request(self.group_width, -1)
        box.add(
            Label(
                name="cheatsheet-group-title",
                style_classes="cheatsheet-group-title",
                label=group["title"],
                h_align="start",
            )
        )

        entries = group["entries"]
        shown_entries = entries[: self.max_entries_per_group]
        for entry in shown_entries:
            row = Box(
                name="cheatsheet-entry",
                style_classes="cheatsheet-entry",
                orientation="h",
                spacing=6,
            )
            row.add(
                Label(
                    name="cheatsheet-key",
                    style_classes="cheatsheet-key",
                    label=entry["keys"],
                    h_align="start",
                    ellipsization="end",
                    max_width_chars=18,
                )
            )
            row.add(
                Label(
                    name="cheatsheet-description",
                    style_classes="cheatsheet-description",
                    label=entry["description"],
                    h_align="start",
                    h_expand=True,
                    ellipsization="end",
                    max_width_chars=36,
                )
            )
            box.add(row)

        if len(entries) > self.max_entries_per_group:
            box.add(
                Label(
                    name="cheatsheet-more",
                    style_classes="cheatsheet-more",
                    label=f"+{len(entries) - self.max_entries_per_group} more",
                    h_align="start",
                )
            )

        return box

    def _set_page(self, page_index):
        if page_index < 0 or page_index >= self.total_pages:
            return

        self.current_page = page_index
        self.stack.set_visible_child_name(f"page-{self.current_page}")
        self.page_label.set_label(f"{self.current_page + 1}/{self.total_pages}")
        self._update_nav_state()

    def _change_page(self, delta):
        self._set_page(self.current_page + delta)

    def _update_nav_state(self):
        is_first = self.current_page == 0
        is_last = self.current_page >= self.total_pages - 1

        self.prev_button.set_sensitive(not is_first)
        self.next_button.set_sensitive(not is_last)

        self.prev_button.set_style_classes(
            ["cheatsheet-nav-btn", "disabled"] if is_first else ["cheatsheet-nav-btn"]
        )
        self.next_button.set_style_classes(
            ["cheatsheet-nav-btn", "disabled"] if is_last else ["cheatsheet-nav-btn"]
        )

    def close(self, *_):
        if self._parent is not None:
            self._parent.hide_popover()


class CheatSheetWidget(ButtonWidget, PopoverMixin):
    """Panel widget that opens Hyprland keybind cheatsheet popover."""

    def __init__(self, **kwargs):
        super().__init__(name="cheatsheet", **kwargs)

        self.add_panel_content(
            self.config.get("icon", "󰌌"),
            self.config.get("label_text", "Keys"),
            show_label=self.config.get("label", True),
        )

        self.set_tooltip_if_enabled(_("widget.cheatsheet.tooltip"), default=True)

        self.setup_popover(lambda: CheatSheetMenu(parent=self, config=self.config))

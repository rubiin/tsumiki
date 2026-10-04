"""Keymap cheatsheet overlay.

The overlay renders keybind *sections* from ``modules.cheatsheet.sections``
instead of querying the compositor, so topics, column count and highlighted
modifiers stay under the user's control.
"""

import re

from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack

from shared.buttons import HoverButton
from shared.popup import PopupWindow
from utils.icons import get_text_icon
from utils.widget_settings import BarConfig
from utils.widget_utils import nerd_font_icon

DEFAULT_TITLE = "Hyprland Keymap"
DEFAULT_ICON = get_text_icon("ui.keyboard")

# Layout constants, sized to the reference look: the key column takes about
# two thirds of a column, the rest is left to the description.
_COLUMN_SPACING = 22
_SECTION_SPACING = 2
_KEY_SPACING = 3
_ENTRY_SPACING = 8
_DESC_MAX_CHARS = 46

# A row's keys may be written as a list or as a spaced string ("Super Shift 3").
_KEY_SPLIT = re.compile(r"[\s+]+")


def normalize_keys(value) -> list[str]:
    """Return the key badges of a row from a list or a spaced string."""
    if isinstance(value, str):
        candidates = _KEY_SPLIT.split(value)
    elif isinstance(value, (list, tuple)):
        candidates = [str(item) for item in value]
    else:
        return []

    return [token for token in (str(item).strip() for item in candidates) if token]


def normalize_row(row) -> dict | None:
    """Return a ``{keys, description}`` row, or ``None`` when it renders empty."""
    if not isinstance(row, dict):
        return None

    keys = normalize_keys(row.get("keys"))
    description = str(row.get("description", "")).strip()
    if not keys and not description:
        return None

    return {"keys": keys, "description": description}


def normalize_section(section) -> dict | None:
    """Return a titled section, or ``None`` when it has no usable rows."""
    if not isinstance(section, dict):
        return None

    rows = [
        row
        for row in (normalize_row(item) for item in section.get("rows") or ())
        if row
    ]
    if not rows:
        return None

    return {"title": str(section.get("title", "")).strip(), "rows": rows}


def normalize_sections(sections) -> list[dict]:
    """Return every renderable section of *sections*, in config order."""
    if not isinstance(sections, (list, tuple)):
        return []

    return [
        section for section in (normalize_section(item) for item in sections) if section
    ]


def section_weight(section: dict) -> int:
    """Row count of *section*, plus its title line."""
    return len(section["rows"]) + 1


def plan_columns(sections: list[dict], columns: int) -> list[list[dict]]:
    """Distribute *sections* over *columns* columns, shortest column first.

    GTK3 has no masonry, so each section lands in the currently shortest
    column; balancing by row count keeps the columns visually even.
    """
    count = max(1, int(columns))
    buckets: list[list[dict]] = [[] for _ in range(count)]
    weights = [0] * count

    for section in sections:
        target = min(range(count), key=weights.__getitem__)
        buckets[target].append(section)
        weights[target] += section_weight(section)

    return buckets


def paginate(sections: list[dict], groups_per_page: int) -> list[list[dict]]:
    """Split *sections* into pages of at most *groups_per_page* sections."""
    per_page = max(1, int(groups_per_page))
    return [
        sections[index : index + per_page]
        for index in range(0, len(sections), per_page)
    ]


class CheatSheetWindow(PopupWindow):
    """Centered overlay listing the configured keybind sections."""

    _instance: "CheatSheetWindow | None" = None

    def __new__(cls, *args, **kwargs):
        # One window per process: the module registry and the bar button both
        # reach for it, and a second surface would fight over the same anchor.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: BarConfig):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self._config_root = config
        self.module_config: dict = {}
        self.columns = 4
        self.column_width = 300
        self.key_width = 190
        self.groups_per_page = 8
        self.accent_keys: set[str] = set()
        self.current_page = 0
        self.total_pages = 1
        self._apply_module_config()

        super().__init__(
            name="cheatsheet-window",
            layer=self.module_config.get("layer", "overlay"),
            anchor=self.module_config.get("anchor", "center"),
            child=self._build_card(),
            transition_type=self.module_config.get("transition_type", "crossfade"),
            transition_duration=self.module_config.get("transition_duration", 200),
            enable_inhibitor=True,
            keyboard_mode="exclusive",
        )

    # ── Configuration ──────────────────────────────────────────

    def _apply_module_config(self) -> None:
        """Read the layout knobs out of the live module config."""
        modules = self._config_root.get("modules") or {}
        self.module_config = modules.get("cheatsheet") or {}
        self.columns = max(1, int(self.module_config.get("columns", 4)))
        self.groups_per_page = max(
            1, int(self.module_config.get("groups_per_page", 8))
        )
        self.column_width = max(80, int(self.module_config.get("column_width", 300)))
        self.key_width = max(0, int(self.module_config.get("key_width", 190)))
        self.accent_keys = {
            str(key).strip().lower()
            for key in self.module_config.get("accent_keys") or ("super",)
        }

    # ── Widget tree ────────────────────────────────────────────

    def _build_card(self) -> EventBox:
        self.title_label = Label(
            name="cheatsheet-title",
            label=self.module_config.get("title", DEFAULT_TITLE),
            h_align="center",
        )
        title = Box(
            name="cheatsheet-title-box",
            orientation="h",
            spacing=8,
            v_align="center",
            children=(
                nerd_font_icon(
                    icon=self.module_config.get("icon", DEFAULT_ICON),
                    props={"name": "cheatsheet-title-icon"},
                ),
                self.title_label,
            ),
        )

        actions = Box(
            name="cheatsheet-actions",
            orientation="h",
            spacing=4,
            v_align="center",
            children=(
                self._build_action(
                    "cheatsheet-refresh",
                    self.module_config.get("refresh_icon", get_text_icon("ui.refresh")),
                    self.refresh,
                ),
                self._build_action(
                    "cheatsheet-close",
                    self.module_config.get("close_icon", ""),
                    self.on_close,
                ),
            ),
        )

        header = Box(
            name="cheatsheet-header",
            orientation="h",
            children=(
                Box(name="cheatsheet-header-fill", h_expand=True),
                title,
                # Both fills expand, so the title stays centered while the
                # actions stay pinned to the trailing edge.
                Box(
                    name="cheatsheet-header-fill",
                    h_expand=True,
                    h_align="end",
                    children=(actions,),
                ),
            ),
        )

        self.stack = Stack(
            name="cheatsheet-stack",
            orientation="v",
            transition_type="crossfade",
            transition_duration=self.module_config.get("transition_duration", 200),
            h_expand=True,
            v_expand=False,
        )

        self.prev_button = self._build_pagination_button(
            "cheatsheet-prev", "<", lambda *_: self.change_page(-1)
        )
        self.next_button = self._build_pagination_button(
            "cheatsheet-next", ">", lambda *_: self.change_page(1)
        )
        self.page_label = Label(
            name="cheatsheet-page-label",
            label="1/1",
            h_align="center",
        )
        self.pagination = Box(
            name="cheatsheet-pagination",
            orientation="h",
            spacing=6,
            h_align="center",
            children=(self.prev_button, self.page_label, self.next_button),
        )

        self._render(normalize_sections(self.module_config.get("sections")))

        # Swallows clicks on the card; the transparent padding around it
        # still closes the overlay.
        return EventBox(
            name="cheatsheet-shield",
            child=Box(
                name="cheatsheet-card",
                orientation="v",
                children=(header, self.stack, self.pagination),
            ),
            events=["button-press"],
            on_button_press_event=lambda *_: True,
        )

    def _build_action(self, name: str, icon: str, callback) -> HoverButton:
        return HoverButton(
            name=name,
            style_classes="cheatsheet-action",
            child=nerd_font_icon(icon=icon, props={"name": f"{name}-icon"}),
            on_clicked=callback,
        )

    def _build_pagination_button(self, name: str, glyph: str, callback) -> HoverButton:
        return HoverButton(
            name=name,
            style_classes="cheatsheet-page-btn",
            child=Label(name=f"{name}-icon", label=glyph),
            on_clicked=callback,
        )

    def _build_section(self, section: dict) -> Box:
        children = []
        if section["title"]:
            children.append(
                Label(
                    name="cheatsheet-section-title",
                    label=section["title"],
                    h_align="start",
                    ellipsization="end",
                )
            )

        children.extend(self._build_entry(row) for row in section["rows"])

        return Box(
            name="cheatsheet-section",
            orientation="v",
            spacing=_SECTION_SPACING,
            children=tuple(children),
        )

    def _build_entry(self, row: dict) -> Box:
        keys = Box(name="cheatsheet-keys", orientation="h", spacing=_KEY_SPACING)
        # Always present, even when a row has no keys, so descriptions in a
        # section all start at the same offset.
        keys.set_size_request(self.key_width, -1)

        for key in row["keys"]:
            style_classes = ["cheatsheet-key"]
            if key.lower() in self.accent_keys:
                style_classes.append("accent")
            keys.add(
                Label(
                    name="cheatsheet-key",
                    style_classes=style_classes,
                    label=key,
                    h_align="start",
                )
            )

        return Box(
            name="cheatsheet-entry",
            orientation="h",
            spacing=_ENTRY_SPACING,
            children=(
                keys,
                Label(
                    name="cheatsheet-description",
                    label=row["description"],
                    h_align="start",
                    h_expand=True,
                    ellipsization="end",
                    max_width_chars=_DESC_MAX_CHARS,
                ),
            ),
        )

    # ── Rendering ──────────────────────────────────────────────

    def _render(self, sections: list[dict]) -> None:
        self.stack.children = ()

        pages = paginate(sections, self.groups_per_page)
        if not pages:
            pages = [[]]

        for index, page_sections in enumerate(pages):
            self.stack.add_named(self._build_page(page_sections), f"page-{index}")

        self.total_pages = len(pages)
        # A single page needs no navigation, matching the plain reference look.
        self.pagination.set_visible(self.total_pages > 1)
        self._set_page(min(self.current_page, self.total_pages - 1))

    def _build_page(self, sections: list[dict]) -> Box:
        page = Box(
            name="cheatsheet-page",
            orientation="h",
            spacing=_COLUMN_SPACING,
        )

        if not sections:
            page.add(
                Label(
                    name="cheatsheet-empty",
                    label="No sections configured in modules.cheatsheet.sections",
                    h_align="center",
                )
            )
            return page

        for column in plan_columns(sections, self.columns):
            column_box = Box(
                name="cheatsheet-column",
                orientation="v",
                spacing=_SECTION_SPACING + 14,
            )
            column_box.set_size_request(self.column_width, -1)

            for section in column:
                column_box.add(self._build_section(section))

            page.add(column_box)

        return page

    # ── Pagination ─────────────────────────────────────────────

    def _set_page(self, page_index: int) -> None:
        self.current_page = max(0, min(page_index, self.total_pages - 1))
        self.stack.set_visible_child_name(f"page-{self.current_page}")
        self.page_label.set_label(f"{self.current_page + 1}/{self.total_pages}")

        for button, is_edge in (
            (self.prev_button, self.current_page == 0),
            (self.next_button, self.current_page >= self.total_pages - 1),
        ):
            button.set_sensitive(not is_edge)
            button.set_style_classes(
                (
                    ["cheatsheet-page-btn", "disabled"]
                    if is_edge
                    else ["cheatsheet-page-btn"]
                )
            )

    def change_page(self, delta: int) -> None:
        self._set_page(self.current_page + delta)

    def refresh(self, *_) -> None:
        """Re-read the section list from the config and rebuild the pages."""
        self._apply_module_config()
        self.title_label.set_label(self.module_config.get("title", DEFAULT_TITLE))
        self._render(normalize_sections(self.module_config.get("sections")))

    def on_close(self, *_) -> None:
        self._set_popup_visible(False)


def toggle_cheatsheet() -> None:
    """Toggle the keymap overlay, creating the window on first use."""
    # Deferred: importing utils.config parses config.toml and validates it.
    from utils.config import tsumiki_config

    CheatSheetWindow(tsumiki_config).toggle_popup()

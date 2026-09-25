import os
from collections.abc import Iterator
from contextlib import suppress
from difflib import SequenceMatcher

from fabric.utils import (
    DesktopApp,
    Gdk,
    GLib,
    Gtk,
    get_relative_path,
    idle_add,
    logger,
    remove_handler,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.grid import Grid
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

from shared.popup import PopupWindow
from utils.app import AppUtils
from utils.decorators import thread
from utils.functions import ttl_lru_cache
from utils.plugin_manager import (
    PluginResult,
    get_plugin_manager,
)
from utils.widget_settings import BarConfig

# Default debounce for plugin queries; plugins can override via debounce_ms.
_PLUGIN_DEBOUNCE_MS = 150

#: Minimum SequenceMatcher ratio for a fuzzy (non-substring) app match.
_FUZZY_MATCH_THRESHOLD = 0.6


@ttl_lru_cache(seconds_to_live=3600, maxsize=4096)
def _score_app_match(app: DesktopApp, query_lower: str) -> float:
    """Return a match score for *app* against a lowercased query.

    ``0.0`` means no match. Substring matches score highest (with a bonus
    for word-boundary prefixes); otherwise an ordered subsequence match
    via :func:`difflib.SequenceMatcher` is accepted above a similarity
    threshold, so "ffx" still finds Firefox but "xyz" doesn't.

    TTL-cached per (app, query): the same query is re-scored on every
    Tab-autocomplete step and on repeat viewport arrangements, so caching
    avoids recomputing SequenceMatcher ratios over all apps each time.
    """
    if not query_lower:
        return 0.0
    text = (
        (app.display_name or "")
        + " "
        + (app.name or "")
        + " "
        + (app.generic_name or "")
    ).casefold()

    if query_lower in text:
        idx = text.find(query_lower)
        if idx == 0 or (idx > 0 and text[idx - 1].isspace()):
            return 110.0  # starts a word (e.g. "fire" finds "Firefox")
        return 100.0

    # Fuzzy fallback: per-field, so long generic names don't dilute it.
    best = 0.0
    for field in (app.display_name, app.name, app.generic_name):
        if not field:
            continue
        ratio = SequenceMatcher(None, query_lower, field.casefold()).ratio()
        if ratio >= _FUZZY_MATCH_THRESHOLD:
            best = max(best, ratio)
    return best * 100.0


class LauncherConfig:
    """Configuration validator and defaults for AppLauncher."""

    # Only essential constants
    DEFAULT_WIDTH = 280
    DEFAULT_HEIGHT = 320
    DEFAULT_ICON_SIZE = 24
    DEFAULT_GRID_COLUMNS = 3
    DEFAULT_GRID_SPACING = 12
    MIN_GRID_ITEM_SIZE = 84
    DEFAULT_ANCHOR = "center"
    DEFAULT_LAYOUT = "list"

    def __init__(self, config: BarConfig):
        self.raw_config = config.get("modules", {}).get("launcher", {})
        self._validate_and_set_defaults()

    def _validate_and_set_defaults(self):
        """Validate configuration and set defaults."""
        self.width = max(200, self.raw_config.get("width", self.DEFAULT_WIDTH))
        self.height = max(200, self.raw_config.get("height", self.DEFAULT_HEIGHT))
        # Height may grow so tall plugin results are visible; width stays fixed.
        self.max_height = max(self.height, int(self.height * 1.5))

        icon_size = self.raw_config.get("icon_size", self.DEFAULT_ICON_SIZE)
        self.icon_size = max(16, min(128, icon_size))

        layout = self.raw_config.get("layout", self.DEFAULT_LAYOUT)
        self.layout_mode = layout if layout in ["list", "grid"] else self.DEFAULT_LAYOUT

        grid_cols = self.raw_config.get("grid_columns", self.DEFAULT_GRID_COLUMNS)
        self.grid_columns = max(1, min(10, grid_cols))

        grid_spacing = self.raw_config.get("grid_spacing", self.DEFAULT_GRID_SPACING)
        self.grid_spacing = max(0, int(grid_spacing))

        # Account for launcher content horizontal padding (10px * 2).
        usable_width = max(0, self.width - 20)
        total_gaps = self.grid_spacing * max(0, self.grid_columns - 1)
        self.grid_item_size = max(
            self.MIN_GRID_ITEM_SIZE,
            (usable_width - total_gaps) // self.grid_columns,
        )

        self.anchor = self.raw_config.get("anchor", self.DEFAULT_ANCHOR)
        self.show_tooltips = bool(self.raw_config.get("tooltip", False))

        # Slash-command plugin system
        self.plugins_enabled = bool(self.raw_config.get("plugins_enabled", True))
        configured_dir = self.raw_config.get("plugins_dir", "")
        self.plugins_dir = os.path.expanduser(
            configured_dir or get_relative_path("../plugins/")
        )
        # Strict allowlist of plugin names to load — an empty list loads none.
        raw_plugins = self.raw_config.get("plugins", [])
        self.plugins = (
            [str(plugin) for plugin in raw_plugins]
            if isinstance(raw_plugins, list)
            else []
        )


class AppWidgetFactory:
    """Factory for creating application widgets in different layouts."""

    @staticmethod
    def create_widget(
        app: DesktopApp, layout_mode: str, icon_size: int, config: LauncherConfig
    ) -> Button:
        """Create an application widget based on layout mode."""
        if layout_mode == "grid":
            child_widget = AppWidgetFactory._create_grid_layout(app, icon_size)
        else:
            child_widget = AppWidgetFactory._create_list_layout(app, icon_size)

        return Button(
            style_classes="launcher-button",
            child=child_widget,
            tooltip_text=(app.description if config.show_tooltips else None),
            h_expand=layout_mode == "grid",
            v_expand=False,
            size_request=(config.grid_item_size, config.grid_item_size)
            if layout_mode == "grid"
            else None,
        )

    @staticmethod
    def _create_grid_layout(
        app: DesktopApp,
        icon_size: int,
    ) -> Box:
        """Create vertical layout for grid mode."""
        label = Label(
            label=app.display_name or "Unknown",
            v_align="center",
            h_align="center",
            justification="center",
            line_wrap="word-char",
            chars_width=12,
            max_chars_width=12,
            ellipsization="end",
            style_classes="grid-item-label",
        )
        label.set_lines(2)

        return Box(
            name="grid-item",
            orientation="v",
            spacing=4,
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            children=[
                Image(
                    pixbuf=app.get_icon_pixbuf(icon_size),
                    h_align="center",
                    name="icon",
                ),
                label,
            ],
        )

    @staticmethod
    def _create_list_layout(
        app: DesktopApp,
        icon_size: int,
    ) -> Box:
        """Create horizontal layout for list mode."""
        return Box(
            name="list-item",
            orientation="h",
            spacing=12,
            style_classes="launcher-list-item",
            children=[
                Image(
                    pixbuf=app.get_icon_pixbuf(icon_size),
                    h_align="start",
                    name="icon",
                ),
                Label(
                    label=app.display_name or "Unknown",
                    v_align="center",
                    h_align="center",
                ),
            ],
        )


class HandlerManager:
    """Context manager for handling GTK handlers safely."""

    def __init__(self, launcher):
        self.launcher = launcher
        self.old_handler = None

    def __enter__(self):
        # Remove old handler if exists and is valid
        if self.launcher._arranger_handler and self.launcher._arranger_handler > 0:
            # Check if the source still exists before removing
            main_context = GLib.MainContext.default()
            handler_id = self.launcher._arranger_handler
            if main_context.find_source_by_id(handler_id):
                try:
                    remove_handler(handler_id)
                    self.old_handler = handler_id
                except (GLib.Error, Exception):
                    # Handler removal failed, just continue silently
                    pass
        self.launcher._arranger_handler = 0
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Cleanup is automatic, nothing to do
        pass

    def set_new_handler(self, handler_id):
        """Set the new handler ID."""
        self.launcher._arranger_handler = handler_id


class Launcher(PopupWindow):
    """Launcher widget for launching applications and commands."""

    _PLUGIN_QUERY_TIMER = "plugin-query"

    def __init__(self, config: dict, **kwargs):
        # Initialize configuration with validation
        self.config = LauncherConfig(config)

        # Initialize remaining instance variables
        self._arranger_handler: int = 0
        self.app_util = AppUtils()
        self._all_apps = self.app_util.all_applications
        self._grid_position = 0  # Track current position in grid
        self._first_app = None  # First app matching the current query (Enter)
        # Rendered app results: (widget, app) pairs in display order.
        self._app_rows: list[tuple[Button, DesktopApp]] = []
        self._app_selected = -1  # Index of the highlighted app result

        # Slash-command plugin state
        self.plugin_manager = (
            get_plugin_manager(self.config.plugins_dir, self.config.plugins)
            if self.config.plugins_enabled
            else None
        )
        self._plugin_mode = False
        self._plugin_command = ""
        self._plugin_args = ""
        self._plugin_rows: list[Button] = []
        self._plugin_selected = 0
        self._plugin_gen = 0
        # Cancel the running plugin worker when a newer query supersedes it.
        self._active_plugin = None

        # Tab-completion cycle state (candidates snapshotted at cycle start).
        self._completion_candidates: list[str] = []
        self._completion_index = -1

        # Create widgets - viewport depends on layout mode
        if self.config.layout_mode == "grid":
            self.viewport = Grid(
                column_homogeneous=True,
                row_homogeneous=False,
                column_spacing=self.config.grid_spacing,
                row_spacing=self.config.grid_spacing,
            )
        else:  # list mode
            self.viewport = Box(spacing=2, orientation="v")
        self.search_entry = Entry(
            name="launcher-prompt",
            placeholder="Search Applications...",
            h_expand=True,
            primary_icon_name="system-search",
            secondary_icon_name="edit-clear",
            notify_text=lambda entry, *_: self.arrange_viewport(entry.get_text()),
        )

        self.search_entry.props.xalign = 0.1
        # Connect handler for icon clicks
        self.search_entry.connect("icon-press", self.on_icon_press)

        self.scrolled_window = ScrolledWindow(
            min_content_size=(self.config.width, self.config.height),
            max_content_size=(self.config.width, self.config.max_height),
            h_expand=True,
            child=self.viewport,
        )

        # Enable kinetic scrolling
        with suppress(AttributeError):
            self.scrolled_window.set_kinetic_scrolling(True)

        # Create the main content
        launcher_content = Box(
            name="launcher-contents",
            spacing=2,
            orientation="v",
            size_request=(self.config.width, self.config.height),
            children=[
                # Header with search
                self.search_entry,
                # Apps list
                self.scrolled_window,
            ],
        )

        # Choose transition based on anchor
        transition = (
            "slide-up" if self.config.anchor.startswith("bottom") else "slide-down"
        )

        super().__init__(
            name="launcher",
            title="launcher",
            anchor=self.config.anchor,
            transition_type=transition,
            transition_duration=300,
            enable_inhibitor=True,
            child=launcher_content,
            **kwargs,
        )

        # Entry handler intercepts Return/arrows; window handler is the fallback.
        self.search_entry.connect("key-press-event", self.on_search_key_press)
        self.connect("key-press-event", self.on_key_press)

    def on_icon_press(self, entry, icon_pos, event):
        if icon_pos == Gtk.EntryIconPosition.SECONDARY:
            self.search_entry.set_text("")

    def close_launcher(self):
        """Close the launcher."""
        self.popup_visible = False
        self.reveal_child.revealer.set_reveal_child(self.popup_visible)
        self.search_entry.set_text("")
        self._reset_plugin_state()

    def on_key_press(self, _, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close_launcher()

    def on_search_key_press(self, entry, event) -> bool:
        """Handle search-entry key shortcuts; True stops default handling."""
        keyval = event.keyval
        if keyval == Gdk.KEY_Escape:
            self.close_launcher()
            return True
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_KP_Tab):
            # Tab cycles the query through every matching result instead of
            # moving focus away from the entry.
            self._autocomplete_query(1)
            return True
        if keyval == Gdk.KEY_ISO_Left_Tab:
            # Shift+Tab cycles backwards.
            self._autocomplete_query(-1)
            return True
        if self._plugin_mode:
            if keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
                self._move_plugin_selection(-1)
                return True
            if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
                self._move_plugin_selection(1)
                return True
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                self._activate_plugin_selection()
                return True
        elif keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            # App-search mode: Up moves the highlight up and scrolls.
            self._move_app_selection(-1)
            return True
        elif keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            # App-search mode: Down moves the highlight down and scrolls.
            self._move_app_selection(1)
            return True
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            # App-search mode: Enter launches the highlighted app.
            self._launch_first_app()
            return True
        return False

    def _autocomplete_query(self, direction: int = 1):
        """Cycle the query through matching results (Tab: +1, Shift+Tab: -1)."""
        text = self.search_entry.get_text()
        if not text:
            self._reset_completion_state()
            return

        # Mid-cycle: the entry still holds the candidate we last set, so just
        # advance/rewind through the snapshot and wrap around.
        if (
            self._completion_candidates
            and 0 <= self._completion_index < len(self._completion_candidates)
            and text == self._completion_candidates[self._completion_index]
        ):
            self._completion_index = (self._completion_index + direction) % len(
                self._completion_candidates
            )
            self._set_search_text(self._completion_candidates[self._completion_index])
            return

        # New query — build a fresh candidate list and start the cycle.
        candidates = self._completion_candidates_for(text)
        if not candidates:
            self._reset_completion_state()
            return
        self._completion_candidates = candidates
        self._completion_index = 0 if direction > 0 else len(candidates) - 1
        self._set_search_text(candidates[self._completion_index])

    def _completion_candidates_for(self, text: str) -> list[str]:
        """Return the cycle candidates for *text* (apps or slash commands)."""
        if self._plugin_mode and text.startswith("/"):
            command, _, args = text[1:].partition(" ")
            command = command.casefold().strip()
            if args or self.plugin_manager is None:
                return []  # already typing args — leave results alone
            return [f"/{p.name} " for p in self.plugin_manager.match(command)]

        query_lower = text.casefold()
        candidates: list[str] = []
        for app in self._all_apps:
            if self._match_score(app, query_lower) <= 0:
                continue
            name = app.display_name or app.name
            if name and name not in candidates:
                candidates.append(name)
        return candidates

    def _reset_completion_state(self):
        """Forget the in-progress Tab cycle (new query / launcher closed)."""
        self._completion_candidates = []
        self._completion_index = -1

    def _set_search_text(self, text: str):
        """Set the search text, moving the caret to the end for continued typing."""
        self.search_entry.set_text(text)
        self.search_entry.grab_focus_without_selecting()
        self.search_entry.set_position(len(text))

    def _launch_first_app(self):
        """Launch the highlighted app, falling back to the first match (Enter)."""
        app = None
        if self._app_selected != -1 and self._app_selected < len(self._app_rows):
            app = self._app_rows[self._app_selected][1]
        if app is None:
            app = self._first_app
        if app is None:
            return
        try:
            app.launch()
        except Exception as exc:
            logger.warning(f"[Launcher] Failed to launch app: {exc}")
            return
        self.close_launcher()

    def _reset_plugin_state(self):
        """Invalidate pending plugin queries and clear selection state."""
        self._cancel_plugin_query_timer()
        self._cancel_active_plugin()
        self._plugin_gen += 1
        self._plugin_mode = False
        self._plugin_rows = []
        self._plugin_selected = 0
        self._plugin_command = ""
        self._plugin_args = ""
        self._reset_completion_state()

    def _clear_viewport_safely(self):
        """Clear viewport widgets with proper error handling."""
        if self.config.layout_mode == "grid":
            try:
                children = [child for child in self.viewport]
                for child in children:
                    self.viewport.remove(child)
            except (AttributeError, TypeError) as e:
                # Log error and recreate grid as fallback
                logger.exception(
                    f"Warning: Grid clear failed ({e}), recreating viewport"
                )
                try:
                    self.viewport = Grid(
                        column_homogeneous=True,
                        row_homogeneous=False,
                        column_spacing=self.config.grid_spacing,
                        row_spacing=self.config.grid_spacing,
                    )
                    self.scrolled_window.set_child(self.viewport)
                except Exception as fallback_error:
                    logger.exception(
                        f"Error: Failed to recreate grid: {fallback_error}"
                    )
        else:
            # For list layout, simple clear
            self.viewport.children = []

    def _prepare_viewport_render(self):
        """Clear viewport state before scheduling a new render pass."""
        self._clear_viewport_safely()
        self._grid_position = 0
        self._first_app = None
        self._app_rows = []
        self._app_selected = -1

    @staticmethod
    def _match_score(app: DesktopApp, query_lower: str) -> float:
        """Return a match score for *app* against a lowercased query.

        Thin wrapper over the TTL-cached :func:`_score_app_match`.
        """
        return _score_app_match(app, query_lower)

    def _filter_applications(self, query: str) -> tuple[Iterator[DesktopApp], bool]:
        """Filter applications by query and return iterator + resize hint.

        Matches are ranked by :meth:`_match_score` (best first); ties keep the
        original application order.
        """
        query_lower = query.casefold()
        if not query_lower:
            filtered_apps = list(self._all_apps)
        else:
            scored = [
                (self._match_score(app, query_lower), app) for app in self._all_apps
            ]
            scored.sort(key=lambda pair: pair[0], reverse=True)
            filtered_apps = [app for score, app in scored if score > 0]
        self._first_app = filtered_apps[0] if filtered_apps else None
        should_resize = len(filtered_apps) == len(self._all_apps)
        return iter(filtered_apps), should_resize

    def _render_step(
        self,
        apps_iter: Iterator[DesktopApp],
        should_resize: bool,
    ) -> bool:
        """Lazy renderer callback used by GLib idle loop."""
        return bool(self.add_next_application(apps_iter))

    def _schedule_viewport_render(
        self,
        apps_iter: Iterator[DesktopApp],
        should_resize: bool,
    ) -> int:
        """Schedule lazy viewport render and return handler id."""
        return idle_add(
            self._render_step,
            apps_iter,
            should_resize,
            pin=True,
        )

    def arrange_viewport(self, query: str = ""):
        """Arrange viewport with filtered applications or plugin results."""
        with HandlerManager(self) as handler_mgr:
            self._prepare_viewport_render()

            if self.plugin_manager is not None and query.startswith("/"):
                handler_id = self._arrange_plugins(query)
            else:
                self._plugin_mode = False
                if self.plugin_manager is None and query.startswith("/"):
                    # Plugins are disabled in config — show a helpful hint.
                    self._render_plugin_hint(
                        "Slash commands are disabled",
                        "Enable modules.launcher.plugins_enabled in config.toml",
                    )
                    handler_id = 0
                else:
                    filtered_apps_iter, should_resize = self._filter_applications(query)
                    handler_id = self._schedule_viewport_render(
                        filtered_apps_iter,
                        should_resize,
                    )

            handler_mgr.set_new_handler(handler_id)

        return False

    # ------------------------------------------------------------------
    # Slash-command plugins
    # ------------------------------------------------------------------

    def _arrange_plugins(self, query: str) -> int:
        """Dispatch a ``/command args`` query to the plugin system."""
        self._cancel_plugin_query_timer()
        self._plugin_mode = True
        self._plugin_rows = []
        self._plugin_selected = 0
        self._plugin_gen += 1
        gen = self._plugin_gen

        command, _, args = query[1:].partition(" ")
        command = command.casefold().strip()
        args = args.strip()

        self._plugin_command = command
        self._plugin_args = args

        if not command:
            # Query is just "/" — browse every available command.
            self._render_command_list("")
            return 0

        plugin = self.plugin_manager.get(command)
        if plugin is None:
            matches = self.plugin_manager.match(command)
            if matches:
                # Partial command name — show matching commands.
                self._render_command_list(command)
            else:
                self._render_plugin_hint(
                    f"Unknown command '/{command}'",
                    "Type / to see available commands",
                )
            return 0

        # Full command match — run the plugin off the main thread and render
        # a lightweight "working" row until the results come back.
        self._render_plugin_hint(
            f"/{plugin.name}{' ' + args if args else ''}",
            "Running...",
        )
        self._schedule_plugin_query(plugin, args, gen)
        return 0

    def _schedule_plugin_query(self, plugin, args: str, gen: int):
        """Debounce plugin dispatch; use the plugin's ``debounce_ms`` override."""
        # A newer query is superseding whatever is still in flight — cancel
        # it now so its subprocess/request is killed rather than wasted.
        self._cancel_active_plugin()

        def _fire() -> bool:
            plugin._reset_cancel()
            self._active_plugin = plugin
            thread(self._plugin_worker, plugin, args, gen)
            return False

        delay = (
            plugin.debounce_ms
            if plugin.debounce_ms and plugin.debounce_ms > 0
            else _PLUGIN_DEBOUNCE_MS
        )
        self._schedule_timeout(self._PLUGIN_QUERY_TIMER, delay, _fire, replace=True)

    def _cancel_plugin_query_timer(self):
        """Cancel a pending debounced plugin query, if any."""
        self._cancel_timeout(self._PLUGIN_QUERY_TIMER)

    def _cancel_active_plugin(self):
        """Kill the in-flight plugin worker, if any."""
        if self._active_plugin is not None:
            self._active_plugin.cancel()
            self._active_plugin = None

    def _plugin_worker(self, plugin, args: str, gen: int):
        """Run a plugin query on a worker thread, then render via idle_add."""
        try:
            results = plugin.handle(args)
        except Exception as exc:
            logger.warning(f"[Launcher] Plugin '/{plugin.name}' failed: {exc}")
            results = [
                PluginResult(
                    f"Plugin '/{plugin.name}' crashed",
                    subtitle=f"{exc}",
                    icon="dialog-error-symbolic",
                )
            ]
        if isinstance(results, PluginResult):
            results = [results]
        elif not isinstance(results, list):
            # Harden against third-party plugins returning a bare value.
            results = [PluginResult(str(results))] if results else []
        idle_add(self._on_plugin_results, gen, plugin, results)

    def _on_plugin_results(self, gen: int, plugin, results: list[PluginResult]) -> bool:
        """Render plugin results, dropping stale or cancelled queries."""
        if gen != self._plugin_gen or not self._plugin_mode:
            return False
        if plugin.is_cancelled():
            return False  # superseded mid-flight — don't render
        self._render_plugin_results(plugin, results)
        return False

    def _render_command_list(self, partial: str):
        """Render available slash commands (browse mode)."""
        plugins = (
            self.plugin_manager.match(partial) if partial else self.plugin_manager.all()
        )
        for plugin in plugins:
            self._append_plugin_row(self._create_command_row(plugin))

    def _render_plugin_results(self, plugin, results: list[PluginResult]):
        """Render plugin result rows, replacing any working/status row."""
        self._prepare_viewport_render()
        if not results:
            hint = f"No results for '/{self._plugin_command} {self._plugin_args}'"
            self._render_plugin_hint(
                hint.rstrip(),
                "Try a different input or type / for available commands",
            )
            return
        for result in results:
            self._append_plugin_row(self._create_plugin_result_row(plugin, result))

    def _render_plugin_hint(self, title: str, subtitle: str = ""):
        """Render a non-interactive status row (hint/error/working)."""
        children = [
            Label(
                label=title,
                h_align="start",
                v_align="center",
                style_classes="launcher-plugin-title",
            )
        ]
        if subtitle:
            children.append(
                Label(
                    label=subtitle,
                    h_align="start",
                    v_align="center",
                    style_classes="launcher-plugin-subtitle",
                )
            )
        box = Box(
            name="launcher-plugin-hint",
            orientation="v",
            spacing=1,
            style_classes=["launcher-list-item"],
            children=children,
        )
        if self.config.layout_mode == "grid":
            self.viewport.attach(box, 0, 0, self.config.grid_columns, 1)
        else:
            self.viewport.add(box)

    def _create_command_row(self, plugin) -> Button:
        """Create a selectable row for a slash command (browse mode)."""
        children = []
        icon = self._plugin_icon_widget(plugin.icon)
        if icon is not None:
            children.append(icon)
        children.append(
            Box(
                orientation="v",
                spacing=1,
                children=[
                    Label(
                        label=f"/{plugin.name}",
                        h_align="start",
                        v_align="center",
                        style_classes="launcher-plugin-title",
                    ),
                    Label(
                        label=plugin.description,
                        h_align="start",
                        v_align="center",
                        style_classes="launcher-plugin-subtitle",
                    ),
                ],
            )
        )
        button = Button(
            style_classes=["launcher-plugin-button"],
            child=Box(
                name="launcher-command-item",
                orientation="h",
                spacing=12,
                style_classes=["launcher-list-item"],
                children=children,
            ),
        )
        # ``on_clicked`` only works as a constructor kwarg — connect explicitly.
        button.connect(
            "clicked",
            lambda *_, p=plugin: self._insert_command(p.name),
        )
        return button

    def _create_plugin_result_row(self, plugin, result: PluginResult) -> Button:
        """Create a selectable row for a single plugin result."""
        children = []
        icon = self._plugin_icon_widget(result.icon or plugin.icon)
        if icon is not None:
            children.append(icon)

        title = Label(
            label=result.title,
            h_align="start",
            v_align="center",
            justification="left",
            ellipsization="end",
            style_classes="launcher-plugin-title",
        )
        if result.subtitle:
            children.append(
                Box(
                    orientation="v",
                    spacing=1,
                    children=[
                        title,
                        Label(
                            label=result.subtitle,
                            h_align="start",
                            v_align="center",
                            justification="left",
                            ellipsization="end",
                            style_classes="launcher-plugin-subtitle",
                        ),
                    ],
                )
            )
        else:
            children.append(title)

        button = Button(
            style_classes=["launcher-plugin-button"],
            child=Box(
                name="launcher-plugin-item",
                orientation="h",
                spacing=12,
                style_classes=["launcher-list-item"],
                children=children,
            ),
        )
        button.connect(
            "clicked",
            lambda *_, p=plugin, r=result: self._execute_plugin_result(p, r),
        )
        return button

    def _plugin_icon_widget(self, icon: str | None):
        """Build an icon widget from a GTK icon name or a Nerd Font glyph."""
        if not icon:
            return None
        if any(ord(ch) > 127 for ch in icon):
            return Label(
                label=icon,
                name="launcher-plugin-icon",
                style_classes=["launcher-plugin-icon-glyph"],
                v_align="center",
            )
        return Image(
            icon_name=icon,
            icon_size=self.config.icon_size,
            name="launcher-plugin-icon",
        )

    def _append_plugin_row(self, button: Button):
        """Add a plugin/command row to the viewport and track selection."""
        index = len(self._plugin_rows)
        self._plugin_rows.append(button)
        if self.config.layout_mode == "grid":
            # Plugin rows span the full width, like list items.
            self.viewport.attach(button, 0, index, self.config.grid_columns, 1)
        else:
            self.viewport.add(button)
        if index == 0:
            button.add_style_class("selected")

    def _move_plugin_selection(self, delta: int):
        """Move the highlighted plugin row by *delta* steps."""
        if not self._plugin_rows:
            return
        old = self._plugin_selected
        new = max(0, min(len(self._plugin_rows) - 1, old + delta))
        if new == old:
            return
        self._plugin_selected = new
        self._plugin_rows[old].remove_style_class("selected")
        self._plugin_rows[new].add_style_class("selected")
        idle_add(self._scroll_to_row, self._plugin_rows[new])

    def _move_app_selection(self, delta: int):
        """Move the highlighted app row by *delta* steps (Up/Down keys)."""
        if not self._app_rows:
            return
        old = self._app_selected
        if old == -1:
            # Start from the top on Down, the bottom on Up.
            new = 0 if delta > 0 else len(self._app_rows) - 1
        else:
            new = old + delta
        new = max(0, min(new, len(self._app_rows) - 1))
        if new == old:
            return
        self._app_selected = new
        if old != -1:
            self._app_rows[old][0].remove_style_class("selected")
        self._app_rows[new][0].add_style_class("selected")
        idle_add(self._scroll_to_row, self._app_rows[new][0])

    def _scroll_to_row(self, button: Button):
        """Scroll the viewport so *button* stays visible while selecting."""
        adj = self.scrolled_window.get_vadjustment()
        alloc = button.get_allocation()
        if alloc.height == 0:
            return False  # Button removed or not yet laid out; stop retrying

        y = alloc.y
        height = alloc.height
        page_size = adj.get_page_size()
        current_value = adj.get_value()

        if y < current_value:
            # Row above the viewport - align to top
            adj.set_value(y)
        elif y + height > current_value + page_size:
            # Row below the viewport - align to bottom
            adj.set_value(y + height - page_size)
        return False

    def _activate_plugin_selection(self):
        """Activate the currently selected plugin row (Enter)."""
        if not self._plugin_rows:
            return
        self._plugin_rows[self._plugin_selected].emit("clicked")

    def _insert_command(self, command: str):
        """Fill the entry with '/<command> ' so the user can type arguments."""
        self._reset_completion_state()
        self._set_search_text(f"/{command} ")

    def _execute_plugin_result(self, plugin, result: PluginResult):
        """Run a plugin action; close the launcher unless it asks to stay open."""
        keep_open = bool(plugin.keep_open)
        try:
            keep_open = keep_open or bool(plugin.execute(result))
        except Exception as exc:
            logger.warning(f"[Launcher] Plugin '/{plugin.name}' execute failed: {exc}")
            keep_open = True
        if not keep_open:
            self.close_launcher()

    def add_next_application(self, apps_iter: Iterator[DesktopApp]):
        """Add the next application widget to the viewport."""
        if not (app := next(apps_iter, None)):
            # Done rendering — highlight the first result by default.
            if self._app_rows and self._app_selected == -1:
                self._app_rows[0][0].add_style_class("selected")
                self._app_selected = 0
            return False

        app_widget = AppWidgetFactory.create_widget(
            app, self.config.layout_mode, self.config.icon_size, self.config
        )
        self._app_rows.append((app_widget, app))
        # Same as above: on_clicked must be a constructor kwarg — connect the
        # signal explicitly so clicking an app tile actually launches it.
        app_widget.connect("clicked", lambda *_: (app.launch(), self.close_launcher()))

        if self.config.layout_mode == "grid":
            app_widget.set_hexpand(True)
            app_widget.set_halign(Gtk.Align.FILL)
            row = self._grid_position // self.config.grid_columns
            col = self._grid_position % self.config.grid_columns
            self.viewport.attach(app_widget, col, row, 1, 1)
            self._grid_position += 1
        else:  # list mode
            self.viewport.add(app_widget)

        return True

    def toggle(self):
        """Toggle launcher visibility."""
        if self.popup_visible:
            self.close_launcher()
        else:
            # Refresh apps list
            self._reset_plugin_state()
            self._all_apps = self.app_util.all_applications
            self.search_entry.set_text("")

            # Focus search entry for filtering
            self.search_entry.grab_focus_without_selecting()

            # Show the popup using PopupWindow's method
            self.toggle_popup()

    def launch(self, command: str):
        self._reset_completion_state()
        self.search_entry.set_text(command)

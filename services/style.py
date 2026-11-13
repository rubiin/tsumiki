import copy
import json
import threading
from collections.abc import Callable
from typing import Any

from fabric import Application
from fabric.core.service import Signal
from fabric.utils import (
    exec_shell_command,
    get_relative_path,
    idle_add,
    logger,
    os,
)

from utils.colors import Colors
from utils.config import tsumiki_config
from utils.constants import CSS_PATH
from utils.decorators import thread
from utils.functions import (
    check_executable_exists,
    exclude_keys,
    flatten_dict,
    read_toml_file,
    update_styling_mode,
    update_theme_config,
)
from utils.widget_colors import (
    format_settings_color_value,
    is_color_literal,
    is_theme_token,
    parse_scss_theme_variables,
)

from .base import SingletonService

# Memoized raw TOML theme data (static files — safe to cache forever).
_MAX_CACHED_THEMES = 64
_theme_file_cache: dict[str, dict] = {}


def _run_inline(callback: Callable[..., None], *args) -> None:
    """Run *callback* now - the inline counterpart of ``idle_add``.

    Same ``(callback, *args)`` shape, so the compile path can be dispatched
    either to the main thread or run where it stands.
    """
    callback(*args)


class StyleService(SingletonService):
    """Centralized service for style/theme management and CSS recompilation."""

    @Signal
    def theme_changed(self, theme_name: str) -> None:
        """Signal emitted after a new theme is applied."""

    @Signal
    def css_recompiled(self) -> None:
        """Signal emitted when CSS has been recompiled and applied."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._themes_dir = get_relative_path("../themes")
        self._styles_dir = get_relative_path("../styles")

        self._compile_lock = threading.Lock()
        self._compiling = False
        self._compile_pending = False

        check_executable_exists("sass")

        self._config = tsumiki_config
        self._styling_config = self._config.get("styling", {})

        self._current_theme: str = self._styling_config.get(
            "theme_name", "catpuccin-mocha"
        )
        self._mode: str = self._styling_config.get("mode", "dark")

        # Cache of available themes (name -> path)
        self._available_themes: list[str] = []
        self._refresh_available_themes()

        # Parsed contents of the currently active theme (the selected mode's section)
        self._theme_contents: dict | None = None

        logger.info(
            f"{Colors.INFO}[StyleService] Initialized with theme="
            f"'{self._current_theme}', mode='{self._mode}'"
        )

    # ── Public properties ──────────────────────────────────────

    @property
    def current_theme(self) -> str:
        """Name of the currently active theme."""
        return self._current_theme

    @property
    def mode(self) -> str:
        """Current color mode ('dark' or 'light')."""
        return self._mode

    @property
    def available_themes(self) -> list[str]:
        """List of available theme names from the themes directory."""
        return list(self._available_themes)

    @property
    def theme_contents(self) -> dict | None:
        """Parsed contents of the active theme (the selected mode's section)."""
        return self._theme_contents

    def get_theme_color_map(self) -> dict[str, str]:
        """Return active theme token map {name: color}."""
        if isinstance(self._theme_contents, dict):
            return {
                str(k): str(v)
                for k, v in self._theme_contents.items()
                if isinstance(k, str) and isinstance(v, str)
            }

        theme_path = f"{self._styles_dir}/_theme.scss"
        try:
            if os.path.exists(theme_path):
                with open(theme_path, "r", encoding="utf-8") as f:
                    return parse_scss_theme_variables(f.read())
        except OSError:
            return {}
        return {}

    # ── Public API ─────────────────────────────────────────────

    def apply_theme_from_config(self) -> None:
        """Load and apply the theme as configured in ``config.toml``."""
        matugen_config = self._styling_config.get("matugen", {})

        if matugen_config.get("enabled", False):
            self._apply_matugen()
        else:
            self._copy_and_apply(self._current_theme, self._mode)

    def apply_theme(self, theme_name: str) -> None:
        """Switch to a different theme by name and persist the choice."""
        if theme_name not in self._available_themes:
            logger.warning(
                f"{Colors.WARNING}[StyleService] Theme '{theme_name}' not found, "
                f"falling back to '{self._available_themes[0]}'"
            )
            theme_name = (
                self._available_themes[0]
                if self._available_themes
                else "catpuccin-mocha"
            )

        self._current_theme = theme_name
        self._copy_and_apply(theme_name, self._mode)

        update_theme_config(theme_name)

        self.emit("theme_changed", theme_name)
        logger.info(f"{Colors.INFO}[StyleService] Applied theme '{theme_name}'")

    def next_theme(self) -> str:
        """Cycle to the next theme in the alphabetical list."""
        if not self._available_themes:
            return self._current_theme

        try:
            idx = self._available_themes.index(self._current_theme)
        except ValueError:
            idx = -1

        next_idx = (idx + 1) % len(self._available_themes)
        next_name = self._available_themes[next_idx]
        self.apply_theme(next_name)
        return next_name

    def previous_theme(self) -> str:
        """Cycle to the previous theme in the alphabetical list."""
        if not self._available_themes:
            return self._current_theme

        try:
            idx = self._available_themes.index(self._current_theme)
        except ValueError:
            idx = 0

        prev_idx = (idx - 1) % len(self._available_themes)
        prev_name = self._available_themes[prev_idx]
        self.apply_theme(prev_name)
        return prev_name

    def set_mode(self, mode: str) -> None:
        """Set the color mode and re-apply the current theme."""
        if mode not in ("dark", "light"):
            logger.warning(
                f"{Colors.WARNING}[StyleService] Invalid mode '{mode}', "
                f"must be 'dark' or 'light'"
            )
            return

        self._mode = mode
        self.apply_theme(self._current_theme)
        # Unchanged here, so this write cannot conflict with apply_theme's.
        update_styling_mode(mode)

    def refresh(self) -> None:
        """Recompile and re-apply the current CSS without changing the theme.

        A refresh landing during a compile is remembered and run once more.
        """
        with self._compile_lock:
            self._compile_pending = True
            if self._compiling:
                logger.info(
                    f"{Colors.INFO}[Theme] CSS compile in flight; queued another pass"
                )
                return
            self._compiling = True
        thread(self._compile_worker)

    def refresh_blocking(self) -> None:
        """Compile and apply CSS synchronously on the calling thread.

        Used at startup so widgets are built already styled; the async path
        mapped them unstyled, then restyled them. Not safe during a compile.
        """
        self._compile_and_apply(_run_inline)

    # ── Internal helpers ───────────────────────────────────────

    def _refresh_available_themes(self) -> None:
        """Scan the themes directory for available ``.toml`` files."""
        try:
            if not os.path.isdir(self._themes_dir):
                logger.warning(
                    f"{Colors.WARNING}[StyleService] Themes directory "
                    f"'{self._themes_dir}' not found"
                )
                self._available_themes = []
                return

            theme_files = sorted(
                f.replace(".toml", "")
                for f in os.listdir(self._themes_dir)
                if f.endswith(".toml")
            )
            self._available_themes = theme_files
        except OSError as exc:
            logger.error(f"{Colors.ERROR}[StyleService] Failed to list themes: {exc}")
            self._available_themes = []

    def _copy_and_apply(self, theme_name: str, mode: str) -> None:
        """Copy a TOML theme file to ``_theme.scss`` (CSS compile is separate)."""
        self._load_theme_contents(theme_name, mode)
        self._write_theme_variables(theme_name, mode)

    def _get_raw_theme(self, theme_name: str) -> dict | None:
        """Return the full parsed TOML for *theme_name*, memoized."""
        if theme_name in _theme_file_cache:
            return _theme_file_cache[theme_name]

        source_file = f"{self._themes_dir}/{theme_name}.toml"
        if not os.path.exists(source_file):
            logger.warning(
                f"{Colors.WARNING}[StyleService] Theme file "
                f"'{theme_name}.toml' not found"
            )
            return None

        contents = read_toml_file(source_file)
        if contents is not None and len(_theme_file_cache) < _MAX_CACHED_THEMES:
            _theme_file_cache[theme_name] = contents
        return contents

    def _load_theme_contents(self, theme_name: str, mode: str) -> None:
        """Parse the theme TOML and cache the active mode's section."""
        contents = self._get_raw_theme(theme_name)
        if contents is None:
            contents = self._get_raw_theme("catpuccin-mocha")

        self._theme_contents = contents.get(mode, contents) if contents else None

    def _write_theme_variables(self, theme: str, mode: str = "dark"):
        """Write flattened theme colors into ``_theme.scss`` (does not run sass)."""
        destination_file = f"{self._styles_dir}/_theme.scss"

        contents = self._get_raw_theme(theme)
        if contents is None:
            logger.warning(
                f"{Colors.WARNING}[StyleService] Theme file "
                f"'{theme}.toml' not found, falling back to default"
            )
            contents = self._get_raw_theme("catpuccin-mocha")

        if contents is None:
            logger.exception(f"{Colors.ERROR}Error: Could not read any theme file.")
            exit(1)

        selected_theme = contents.get(mode, contents)
        logger.info("[CONFIG] Generating theme css...")
        self.write_css_file(flatten_dict(selected_theme), destination_file)

    def write_css_file(self, contents, file, header: str = ""):
        """Generate SCSS settings file from flattened config."""

        css_styles = contents

        # Use list comprehension and join for faster string building
        lines = [
            f"${setting}: {json.dumps(value) if isinstance(value, bool) else value};"
            for setting, value in css_styles.items()
        ]

        with open(file, "w") as f:
            if header:
                f.write(header)
                if not header.endswith("\n"):
                    f.write("\n")
            f.write("\n".join(lines))
            f.write("\n")

    def _apply_matugen(self) -> None:
        """Generate colors via Matugen and apply them."""
        try:
            from services import matugen_service

            # Run synchronously at startup
            matugen_service.generate_sync()
            # Matugen themes don't have a parsable TOML contents cache
            self._theme_contents = None
            self.emit("theme_changed", "matugen")
        except Exception as exc:
            logger.exception(
                f"{Colors.ERROR}[StyleService] Matugen generation failed: {exc}"
            )

    # ── CSS compilation (moved from utils/functions.py) ─────────

    @staticmethod
    def _apply_css_to_app(file):
        """Load the compiled CSS file into the running application."""
        try:
            if file:
                with open(file, encoding="utf-8") as handle:
                    content = handle.read()
                # Belt-and-braces: GTK3 rejects @charset as an unknown @ rule,
                # but the compile passes --no-charset, so skip the rewrite.
                if "@charset" in content:
                    stripped = "\n".join(
                        line
                        for line in content.splitlines()
                        if not line.lstrip().startswith("@charset")
                    )
                    if stripped != content:
                        with open(file, "w", encoding="utf-8") as handle:
                            handle.write(stripped)
            app = Application.get_default()
            if app:
                app.set_stylesheet_from_file(file)
                logger.info(f"{Colors.INFO}[Theme] CSS applied to application")
        except Exception as e:
            logger.exception(f"{Colors.ERROR}[Theme] Error applying CSS to app: {e}")

    def _compile_worker(self) -> None:
        """Compile while refreshes are queued, applying each result in turn."""
        try:
            while True:
                with self._compile_lock:
                    if not self._compile_pending:
                        self._compiling = False
                        return
                    self._compile_pending = False
                self._compile_and_apply(idle_add)
        except Exception as exc:
            # A stuck flag would silently drop every later refresh.
            with self._compile_lock:
                self._compiling = False
                self._compile_pending = False
            logger.exception(f"{Colors.ERROR}[Theme] CSS compile worker failed: {exc}")

    def _compile_and_apply(self, dispatch: Callable[..., None]) -> None:
        """Run ``sass`` once and route the result through *dispatch*.

        The worker passes ``idle_add`` so the apply lands on the main thread;
        the startup path passes ``_run_inline`` to run where it stands.
        """
        logger.info(f"{Colors.INFO}[Theme] Recompiling CSS")
        # --no-charset: dart-sass emits @charset, which GTK3 rejects.
        output = exec_shell_command(
            f"sass styles/main.scss {CSS_PATH} --no-source-map --no-charset"
        )

        if output == "":
            logger.info(f"{Colors.INFO}[Theme] CSS compiled")
            dispatch(self._finish_compile, get_relative_path(CSS_PATH))
            return

        logger.exception(f"{Colors.ERROR}[Main]Failed to compile sass!")
        logger.exception(f"{Colors.ERROR}[Main] {output}")
        dispatch(self._finish_compile, "")

    def _finish_compile(self, css_file: str) -> None:
        """Apply the compiled stylesheet, then announce it as applied."""
        self._apply_css_to_app(css_file)
        self.emit("css_recompiled")

    def write_settings_css(self):
        logger.info("[CONFIG] Generating settings css...")
        styling = copy.deepcopy(
            exclude_keys(self._config.get("styling", {}), ["matugen"])
        )
        if styling.get("bar", {}).get("monochrome", False):
            self._strip_bar_widget_colors(styling)
        theme_tokens = set(self.get_theme_color_map().keys())
        self._transform_color_settings(styling, theme_tokens=theme_tokens)
        self.write_css_file(
            flatten_dict(styling),
            f"{self._styles_dir}/_settings.scss",
            header='@use "theme";',
        )

    @staticmethod
    def _strip_bar_widget_colors(styling: dict) -> None:
        """Remove per-widget bar color overrides when monochrome is enabled.

        Battery and weather keep their colors in all modes.
        """
        bar = styling.get("bar")
        if not isinstance(bar, dict):
            return
        widgets = bar.get("widgets")
        if not isinstance(widgets, dict):
            return
        always_colored = {"battery", "weather"}
        for widget_name, widget_cfg in widgets.items():
            if widget_name in always_colored or not isinstance(widget_cfg, dict):
                continue
            widget_cfg.pop("colors", None)
            overrides = widget_cfg.get("overrides")
            if isinstance(overrides, dict):
                for override_cfg in overrides.values():
                    if isinstance(override_cfg, dict):
                        override_cfg.pop("colors", None)

    def _transform_color_settings(
        self,
        node,
        in_colors: bool = False,
        *,
        theme_tokens: set[str] | None = None,
        path: list[str] | None = None,
    ):
        """Convert/validate widget color settings for SCSS emission."""
        path = path or []
        if isinstance(node, dict):
            for key, value in list(node.items()):
                next_path = [*path, str(key)]
                next_in_colors = in_colors or key == "colors"
                if isinstance(value, (dict, list)):
                    self._transform_color_settings(
                        value,
                        next_in_colors,
                        theme_tokens=theme_tokens,
                        path=next_path,
                    )
                elif next_in_colors:
                    context = self._build_color_context(next_path)
                    if _is_unset_color_setting(value):
                        node.pop(key, None)
                        continue
                    if is_color_literal(value):
                        continue
                    if isinstance(value, str) and is_theme_token(value):
                        if theme_tokens is not None and value not in theme_tokens:
                            self._warn_invalid_color_setting(value, context)
                            node.pop(key, None)
                            continue
                        formatted = format_settings_color_value(
                            value, theme_tokens=theme_tokens
                        )
                        if formatted is not None:
                            node[key] = formatted
                        else:
                            self._warn_invalid_color_setting(value, context)
                            node.pop(key, None)
                        continue
                    # malformed/non-string/invalid
                    self._warn_invalid_color_setting(value, context)
                    node.pop(key, None)
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                self._transform_color_settings(
                    item,
                    in_colors,
                    theme_tokens=theme_tokens,
                    path=[*path, str(idx)],
                )

    @staticmethod
    def _build_color_context(path: list[str]) -> dict[str, str | None]:
        context: dict[str, str | None] = {
            "widget_type": None,
            "instance_id": None,
            "state": None,
            "field": None,
        }
        try:
            if len(path) >= 4 and path[0] == "bar" and path[1] == "widgets":
                context["widget_type"] = path[2]
                # <type>.colors[.state].field or <type>.overrides.<id>.colors...
                if "colors" in path:
                    ci = path.index("colors")
                    if ci >= 4 and path[3] == "overrides":
                        context["instance_id"] = path[4]
                    tail = path[ci + 1 :]
                    if len(tail) == 1:
                        context["field"] = tail[0]
                    elif len(tail) >= 2:
                        context["state"] = tail[0]
                        context["field"] = tail[1]
        except Exception:
            pass
        return context

    @staticmethod
    def _warn_invalid_color_setting(value, context: dict[str, str | None]) -> None:
        parts = []
        for key in ("widget_type", "instance_id", "state", "field"):
            v = context.get(key)
            if v:
                parts.append(f"{key}={v}")
        suffix = f" ({', '.join(parts)})" if parts else ""
        logger.warning(
            f"{Colors.WARNING}[StyleService] Ignoring invalid widget color value "
            f"{value!r}{suffix}"
        )


def _is_unset_color_setting(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


style_service = StyleService()

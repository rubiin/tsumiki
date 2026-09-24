import importlib

from fabric import Application
from fabric.utils import (
    GLib,
    get_relative_path,
    logger,
    monitor_file,
    os,
)

import utils.functions as helpers
from modules.bar import Bar
from utils.colors import Colors
from utils.config import tsumiki_config
from utils.constants import APP_DATA_DIRECTORY, APPLICATION_NAME
from utils.i18n import get_i18n


def main():
    """Main function to run the application."""
    # Defer config loading until main() is called

    general_options = tsumiki_config.get("general") or {}

    module_options = tsumiki_config.get("modules") or {}

    def module_enabled(name: str) -> bool:
        return bool((module_options.get(name) or {}).get("enabled", False))

    helpers.ensure_directory(APP_DATA_DIRECTORY)

    # Initialize i18n with the configured language
    language = general_options.get("language", "en")
    i18n = get_i18n()
    i18n.load(language)

    # Initialize theme service and apply the configured theme
    from services import style_service

    style_service.write_settings_css()
    style_service.apply_theme_from_config()

    helpers.set_process_name(APPLICATION_NAME)

    # Initialize the application
    app = Application(APPLICATION_NAME)

    # Compile and apply the stylesheet before any widget exists. Building the
    # bars first meant they were mapped unstyled and restyled once the first
    # async compile landed - a second full style/layout pass and a flash.
    style_service.refresh_blocking()

    # Create status bars
    Bar.create_bars(app, tsumiki_config)

    # ── Module registry: config key → (module path, class name) ──────────
    module_registry = {
        "notification": ("modules.notification", "NotificationPopup"),
        "overview": ("modules.overview", "OverViewOverlay"),
        "screen_corners": ("modules.corners", "ScreenCorners"),
        "desktop_quotes": ("modules.desktop_quotes", "DesktopQuote"),
        "activate_linux": ("modules.activate_linux", "ActivateLinux"),
        "launcher": ("modules.launcher", "Launcher"),
        "dock": ("modules.dock", "Dock"),
        "desktop_clock": ("modules.desktop_clock", "DesktopClock"),
        "osd": ("modules.osd", "OSDContainer"),
    }

    for name, (module_path, class_name) in module_registry.items():
        if module_enabled(name):
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            logger.info(f"[Main] Adding {name} module")
            app.add_window(cls(tsumiki_config))

    # Disable verbose logging for non-debug mode

    if not general_options.get("debug", False):
        for log in [
            "fabric",
            "widgets",
            "utils",
            "utils.config",
            "modules",
            "services",
            "config",
        ]:
            logger.disable(log)

    # Start config file watching if enabled
    if general_options.get("auto_restart", True):
        from utils.config_watcher import start_config_watching

        start_config_watching()

    if general_options.get("monitor_styles", False):
        main_css_file = monitor_file(get_relative_path("styles"))
        common_css_file = monitor_file(get_relative_path("styles/common"))
        css_reload_timeout_id = 0
        css_reload_debounce_ms = 200

        def schedule_css_reload(*_):
            nonlocal css_reload_timeout_id
            if css_reload_timeout_id:
                GLib.source_remove(css_reload_timeout_id)

            css_reload_timeout_id = GLib.timeout_add(
                css_reload_debounce_ms,
                lambda: (style_service.refresh(), False),
            )

        main_css_file.connect("changed", schedule_css_reload)
        common_css_file.connect("changed", schedule_css_reload)

    logger.info(f"{Colors.INFO}[Main] Starting {APPLICATION_NAME}...")
    logger.info(f"Starting shell... pid:{os.getpid()}")

    @Application.action()
    def toggle_window(name: str):
        logger.info("[Main] Toggling window", name)
        available_windows = [window.get_name() for window in app.get_windows()]

        if name not in available_windows:
            logger.warning(
                f"{Colors.WARNING}[Main] No window named '{name}' found!",
                f"Available windows: {available_windows}",
            )
            return False

        window = next((w for w in app.get_windows() if w.get_name() == name), None)
        if window:
            window.toggle()

        return False

    @Application.action()
    def open_inspector():
        app.open_inspector()

        return False

    @Application.action()
    def list_windows():
        """List all available windows."""
        windows = {}
        for window in app.get_windows():
            windows[window.get_name()] = window.get_visible()
        return str(windows)

    @Application.action()
    def reload_config():
        """Reload Tsumiki configuration."""
        try:
            from utils.config import TsumikiConfig

            config = TsumikiConfig()
            config._load_config()
            logger.info("[Main] Configuration reloaded")
            return ""
        except Exception as e:
            logger.error(f"[Main] Failed to reload config: {e}")
            return str(e)

    @Application.action()
    def execute_command(command: str):
        """Execute a shell command and return the output."""
        import subprocess

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout
            if result.returncode != 0:
                output += f"\nError: {result.stderr}"
            return output
        except subprocess.TimeoutExpired:
            return "Command timed out after 10 seconds"
        except Exception as e:
            return f"Error: {e}"

    # Run the application
    app.run()


if __name__ == "__main__":
    main()

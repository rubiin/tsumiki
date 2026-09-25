import importlib

from fabric import Application
from fabric.utils import exec_shell_command_async, logger
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer

from shared.widget_container import BaseWindow
from utils.constants import ASSETS_DIR
from utils.widget_settings import BarConfig


class LazyWidgetDict(dict):
    """A dict that lazily imports widget classes on first access (faster startup)."""

    def __init__(self, widget_paths: dict[str, str]):
        super().__init__()
        self._paths = widget_paths
        self._cache = {}

    def __getitem__(self, key: str):
        # Return cached class if already imported
        if key in self._cache:
            return self._cache[key]

        # Check if we have a path for this widget
        if key not in self._paths:
            raise KeyError(f"Widget '{key}' not found")

        # Dynamically import the widget class
        class_path = self._paths[key]
        module_name, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        widget_class = getattr(module, class_name)

        # Cache and return
        self._cache[key] = widget_class
        return widget_class

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        return key in self._paths

    def __bool__(self) -> bool:
        """Return True if there are any widget paths defined."""
        return bool(self._paths)

    def __len__(self) -> int:
        """Return the number of widget paths defined."""
        return len(self._paths)

    def keys(self):
        return self._paths.keys()

    def items(self):
        # For iteration, import all (used by WidgetGroup)
        for key in self._paths:
            yield key, self[key]


# Lazy widget loading - widgets are imported on-demand to speed up startup
# Format: "widget_name": "module.path.ClassName"
LAZY_WIDGETS_LIST = {
    "launcher_button": "widgets.launcher_button.LauncherButton",
    "battery": "widgets.battery.BatteryWidget",
    "bluetooth": "widgets.bluetooth.BlueToothWidget",
    "brightness": "widgets.brightness.BrightnessWidget",
    "cava": "widgets.cava.CavaWidget",
    "cheatsheet": "widgets.cheatsheet.CheatSheetWidget",
    "click_counter": "widgets.click_counter.ClickCounterWidget",
    "breathe": "widgets.breathing.BreatheWidget",
    "clipboard": "widgets.clipboard.ClipBoardWidget",
    "collapsible_group": "shared.collapsible_group.CollapsibleGroupWidget",
    "custom_button": "shared.custom_button.CustomButtonWidget",
    "cpu": "widgets.stats.CpuWidget",
    "custom_widget": "widgets.custom_widget.CustomWidget",
    "date_time": "widgets.datetime_menu.DateTimeWidget",
    "divider": "widgets.utility_widgets.DividerWidget",
    "emoji_picker": "widgets.emoji_picker.EmojiPickerWidget",
    "gpu": "widgets.stats.GpuWidget",
    "hypridle": "widgets.hypridle.HyprIdleWidget",
    "hyprpicker": "widgets.hyprpicker.HyprPickerWidget",
    "hyprsunset": "widgets.hyprsunset.HyprSunsetWidget",
    "ip_monitor": "widgets.ip_monitor.IPMonitorWidget",
    "kanban": "widgets.kanban.KanbanWidget",
    "keyboard": "widgets.keyboard_layout.KeyboardLayoutWidget",
    "language": "widgets.language.LanguageWidget",
    "memory": "widgets.stats.MemoryWidget",
    "microphone": "widgets.microphone.MicrophoneIndicatorWidget",
    "mpris": "widgets.mpris.MprisWidget",
    "network_usage": "widgets.stats.NetworkUsageWidget",
    "ocr": "widgets.ocr.OCRWidget",
    "overview_button": "widgets.overview_button.OverviewButtonWidget",
    "power": "widgets.power_button.PowerWidget",
    "quick_settings": "widgets.quick_settings.quick_settings.QuickSettingsButtonWidget",
    "pomodoro": "widgets.pomodoro.PomodoroWidget",
    "recorder": "widgets.recorder.RecorderWidget",
    "screenshot": "widgets.screenshot.ScreenShotWidget",
    "settings": "widgets.settings.SettingsWidget",
    "spacing": "widgets.utility_widgets.SpacingWidget",
    "stopwatch": "widgets.stopwatch.StopWatchWidget",
    "storage": "widgets.stats.StorageWidget",
    "submap": "widgets.submap.SubMapWidget",
    "system_tray": "widgets.system_tray.SystemTrayWidget",
    "taskbar": "widgets.taskbar.TaskBarWidget",
    "theme_switcher": "widgets.theme.ThemeSwitcherWidget",
    "updates": "widgets.updates.UpdatesWidget",
    "usb_manager": "widgets.usb_manager.USBManagerWidget",
    "volume": "widgets.volume.VolumeWidget",
    "wallpaper": "widgets.wallpaper.WallpaperWidget",
    "weather": "widgets.weather.WeatherWidget",
    "window_count": "widgets.window_count.WindowCountWidget",
    "window_title": "widgets.window_title.WindowTitleWidget",
    "workspaces": "widgets.workspaces.WorkSpacesWidget",
    "world_clock": "widgets.world_clock.WorldClockWidget",
    "github_tray": "widgets.github_tray.widget.GitHubTrayWidget",
    "cloudflare_warp": "widgets.cloudflare_warp.CloudflareWarpWidget",
    "dns_switcher": "widgets.dns_switcher.DnsSwitcherWidget",
}


class Bar(BaseWindow):
    """A widget to display the status bar panel."""

    _HIDE_TIMER = "auto-hide"

    def __init__(self, config: BarConfig, **kwargs):
        # Use lazy widget loading - classes are imported on first use
        self.widgets_list = LazyWidgetDict(LAZY_WIDGETS_LIST)

        options = config.get("general", {})
        bar_config = config.get("modules", {}).get("bar", {})
        layout = self.make_layout(config)

        # Auto-hide configuration
        self._auto_hide = bar_config.get("auto_hide", False)
        self._auto_hide_timeout = bar_config.get("auto_hide_timeout", 3000)
        self._is_hovered = False

        # Main bar content (back to original CenterBox layout)
        self.box = CenterBox(
            name="panel-inner",
            start_children=layout["left_section"],
            center_children=layout["middle_section"],
            end_children=layout["right_section"],
        )

        anchor = f"left {bar_config.get('location', 'top')} right"
        location = bar_config.get("location", "top")

        # Only use revealer/eventbox if auto-hide is enabled
        if self._auto_hide:
            # Determine transition type based on bar location
            transition_type = "slide-down" if location == "top" else "slide-up"

            # Create revealer for auto-hide functionality
            self.revealer = Revealer(
                child=self.box,
                transition_type=transition_type,
                transition_duration=300,
                reveal_child=True,
            )

            # Create a hover zone that remains visible even when bar is hidden
            # This allows the user to hover at the edge to reveal the bar
            hover_zone = Box(style="min-height: 5px;")

            # Stack the revealer and hover zone
            if location == "top":
                container = Box(
                    orientation="v",
                    children=[self.revealer, hover_zone],
                )
            else:
                container = Box(
                    orientation="v",
                    children=[hover_zone, self.revealer],
                )

            # Wrap in event box to detect mouse hover
            child = EventBox(
                events=["enter-notify", "leave-notify"],
                child=container,
                on_enter_notify_event=self._on_enter_notify,
                on_leave_notify_event=self._on_leave_notify,
            )
        else:
            self.revealer = None
            child = self.box

        super().__init__(
            name="panel",
            layer=bar_config.get("layer", "top"),
            anchor=anchor,
            pass_through=False,
            exclusivity="auto",
            visible=True,
            all_visible=False,
            child=child,
            **kwargs,
        )

        # Start auto-hide timer if enabled
        if self._auto_hide:
            self._start_hide_timer()

        if options["check_updates"]:
            exec_shell_command_async(
                f"{ASSETS_DIR}/scripts/barupdate.sh",
                lambda _: None,
            )

    def _on_enter_notify(self, *_):
        """Handle mouse entering the bar area."""
        self._is_hovered = True
        self._cancel_hide_timer()
        self.revealer.set_reveal_child(True)
        return False

    def _on_leave_notify(self, *_):
        """Handle mouse leaving the bar area."""
        self._is_hovered = False
        if self._auto_hide:
            self._start_hide_timer()
        return False

    def _start_hide_timer(self):
        """Start the timer to hide the bar after inactivity."""
        self._schedule_timeout(
            self._HIDE_TIMER,
            self._auto_hide_timeout,
            self._hide_bar,
            replace=True,
        )

    def _cancel_hide_timer(self):
        """Cancel any pending hide timer."""
        self._cancel_timeout(self._HIDE_TIMER)

    def _hide_bar(self):
        """Hide the bar if not hovered."""
        if not self._is_hovered:
            self.revealer.set_reveal_child(False)
        return False  # Don't repeat the timeout

    def make_layout(self, config: BarConfig):
        """assigns the three sections their respective widgets"""
        from utils.widget_factory import WidgetResolver

        layout = {"left_section": [], "middle_section": [], "right_section": []}

        # Create a single resolver for all widgets - now truly unified!
        resolver = WidgetResolver(self.widgets_list)
        context = {"config": config}

        for key in layout:
            for widget_name in config["layout"][key]:
                # Use unified widget resolver for ALL widget types
                widget = resolver.resolve_widget(widget_name, context)
                if widget:
                    # Mark top-level bar widgets so CSS can target them directly
                    # (e.g. for spacing) without depending on the CenterBox tree
                    widget.add_style_class("panel-widget")
                    layout[key].append(widget)

        return layout

    @staticmethod
    def create_bars(app: Application, config: BarConfig) -> list:
        multi_monitor = config.get("general", {}).get("multi_monitor", False)
        if multi_monitor:
            Bar._create_multi_monitor_bars_async(
                app,
                config,
                lambda bars: Bar._setup_hotplug(app, config, bars),
            )
            return []
        else:
            bar = Bar(config)
            app.add_window(bar)
            return [bar]

    @staticmethod
    def _create_multi_monitor_bars_async(app: Application, config: BarConfig, callback):
        """Fetch monitor names asynchronously, create per-monitor bars."""
        from utils.monitors import HyprlandWithMonitors

        monitor_util = HyprlandWithMonitors()
        monitor_util.get_monitor_names(
            lambda names: Bar._on_monitor_names_fetched(app, config, names, callback)
        )

    @staticmethod
    def _on_monitor_names_fetched(
        app: Application, config: BarConfig, monitor_names: list[str], callback
    ):
        from utils.monitors import HyprlandWithMonitors

        if not monitor_names:
            bar = Bar(config)
            app.add_window(bar)
            callback([bar])
            return

        monitor_util = HyprlandWithMonitors()
        bars = []
        for monitor_name in monitor_names:
            monitor_id = monitor_util.get_gdk_monitor_id_from_name(monitor_name)
            if monitor_id is not None:
                bars.append(Bar(config, monitor=monitor_id))

        if not bars:
            bars = [Bar(config)]

        for bar in bars:
            app.add_window(bar)

        callback(bars)

    @staticmethod
    def _setup_hotplug(app: Application, config: BarConfig, bars: list):
        from utils.monitors import MonitorWatcher

        watcher = MonitorWatcher()

        watcher.add_callback(lambda: Bar._recreate_bars(app, config, bars))
        watcher.start_watching()

    @staticmethod
    def _recreate_bars(app: Application, config: BarConfig, bars: list):
        # Remove old
        for bar in bars:
            try:
                app.remove_window(bar)
                bar.destroy()
            except Exception:
                logger.exception("Error removing old bar during hotplug handling")

        # Create new bars asynchronously
        bars.clear()
        Bar._create_multi_monitor_bars_async(
            app, config, lambda new_bars: bars.extend(new_bars)
        )

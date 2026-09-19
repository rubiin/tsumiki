from typing import TypedDict

from .types import (
    Anchor,
    Bar_Location,
    Data_Unit,
    Dock_Behavior,
    Layer,
    Orientation,
    Osd_Type,
    Power_Options,
    Return_Type,
    Reveal_Animations,
    Slider_Type,
    Temperature_Unit,
    Title_Fallback,
    Weather_Provider,
    Widget_Mode,
    Wind_Speed_Unit,
)

# Common configuration fields that will be reused
BaseConfig = TypedDict("BaseConfig", {"label": bool, "tooltip": bool})

# Layout configuration
Layout = TypedDict(
    "Layout", {"left": list[str], "middle": list[str], "right": list[str]}
)


# WallPaper configuration
WallPaper = TypedDict(
    "WallPaper",
    {
        "icon": str,
        "label": bool,
        "tooltip": bool,
    },
)

# Power button configuration
PowerButton = TypedDict(
    "PowerButton",
    {
        "icon": str,
        "tooltip": bool,
        "items_per_row": int,
        "icon_size": int,
        "label": bool,
        "show_icon": bool,
        "confirm": bool,
        "buttons": dict[
            dict[
                Power_Options,
                str,
            ],
            str,
        ],
    },
)

# HyprSunset configuration
HyprSunset = TypedDict(
    "HyprSunset",
    {
        **BaseConfig.__annotations__,
        "temperature": str,
        "enabled_icon": str,
        "disabled_icon": str,
    },
)

# TaskBar configuration
TaskBar = TypedDict(
    "TaskBar",
    {
        "icon_size": int,
        "ignored": list[str],
        "tooltip": bool,
        "show_current_workspace_only": bool,
    },
)

# SystemTray configuration
SystemTray = TypedDict(
    "SystemTray",
    {
        "icon_size": int,
        "ignored": list[str],
        "hidden": list[str],
        "hide_when_empty": bool,
        "tooltip": bool,
    },
)


# HyprIdle configuration
HyprIdle = TypedDict(
    "HyprIdle",
    {**BaseConfig.__annotations__, "enabled_icon": str, "disabled_icon": str},
)

# Window Count configuration
WindowCount = TypedDict(
    "WindowCount",
    {
        **BaseConfig.__annotations__,
        "label_format": str,
        "hide_when_zero": bool,
    },
)

# Battery configuration
Battery = TypedDict(
    "Battery",
    {
        "tooltip": bool,
        "label_format": str,
        "full_battery_level": int,
        "hide_when_missing": bool,
        "notifications": dict,
        "hide_percent_when_full": bool,
        "icons": list[str],
    },
)

# Theme configuration
Theme = TypedDict("Theme", {"name": str})

# ClickCounter configuration
ClickCounter = TypedDict("ClickCounter", {"count": int})

# StopWatch configuration
StopWatch = TypedDict(
    "StopWatch",
    {
        "stopped_icon": str,
        "running_icon": str,
    },
)

Notification_Timeout = TypedDict(
    "Notification_Timeout",
    {
        "low": int,
        "normal": int,
        "critical": int,
    },
)


Notification_Persist = TypedDict(
    "Notification_Persist",
    {
        "enabled": bool,
        "low": bool,
        "normal": bool,
        "critical": bool,
        "max_count": int,
    },
)

# Notification configuration
Notification = TypedDict(
    "Notification",
    {
        "enabled": bool,
        "ignored": list[str],
        "timeout": Notification_Timeout,
        "max_lines": int,
        "max_expanded_lines": int,
        "anchor": Anchor,
        "auto_dismiss": bool,
        "respect_expire": bool,
        "persist": Notification_Persist,
        "play_sound": bool,
        "sound_file": str,
        "dismiss_on_hover": bool,
        "dnd_on_screencast": bool,
        "max_actions": int,
        "copy_code_action": bool,
        "show_timestamp": bool,
        "per_app_limits": dict[str, int],
        "transition_type": Reveal_Animations,
        "transition_duration": int,
    },
)

# DesktopClock configuration
DesktopClock = TypedDict(
    "DesktopClock",
    {
        "enabled": bool,
        "anchor": Anchor,
        "layer": Layer,
        "date_format": str,
        "time_format": str,
    },
)

# Quotes configuration
DesktopQuotes = TypedDict(
    "DesktopQuotes",
    {
        "enabled": bool,
        "anchor": Anchor,
        "layer": Layer,
        "interval": int,
    },
)


# ActivateLinux configuration
ActivateLinux = TypedDict(
    "ActivateLinux",
    {
        "enabled": bool,
        "anchor": Anchor,
        "layer": Layer,
    },
)


# Overview configuration
Overview = TypedDict(
    "Overview",
    {
        "enabled": bool,
        "anchor": Anchor,
        "layer": Layer,
        "transition_type": Reveal_Animations,
        "transition_duration": int,
    },
)

# Overview configuration
Cheatsheet = TypedDict(
    "Cheatsheet",
    {
        "enabled": bool,
        "anchor": Anchor,
        "layer": Layer,
        "transition_type": Reveal_Animations,
        "transition_duration": int,
    },
)

# ScreenCorners configuration
ScreenCorners = TypedDict(
    "ScreenCorners",
    {"enabled": bool, "size": int},
)

# OSD configuration
OSD = TypedDict(
    "Osd",
    {
        "enabled": bool,
        "timeout": int,
        "anchor": Anchor,
        "percentage": bool,
        "icon_size": int,
        "play_sound": bool,
        "transition_type": Reveal_Animations,
        "transition_duration": int,
        "osds": list[Osd_Type],
    },
)


# Dock configuration
Dock = TypedDict(
    "Dock",
    {
        "enabled": bool,
        "tooltip": bool,
        "orientation": Orientation,
        "behavior": Dock_Behavior,
        "show_launcher": bool,
        "launcher_position": str,
        "icon_size": int,
        "show_when_no_windows": bool,
        "group_apps": bool,
        "truncation_size": int,
        "ignored": list[str],
        "always_show_focused": bool,
        "hide_special_workspace_apps": bool,
        "layer": Layer,
    },
)


# Launcher configuration
Launcher = TypedDict(
    "Launcher",
    {
        "enabled": bool,
        "tooltip": bool,
        "icon_size": int,
        "plugins_enabled": bool,
        "plugins_dir": str,
        "plugins": list[str],
    },
)


Bar = TypedDict(
    "Bar",
    {
        "location": Bar_Location,
        "layer": Layer,
        "auto_hide": bool,
        "auto_hide_timeout": int,
    },
)


# Modules configuration
Modules = TypedDict(
    "Modules",
    {
        "dock": Dock,
        "bar": Bar,
        "desktop_quotes": DesktopQuotes,
        "osd": OSD,
        "desktop_clock": DesktopClock,
        "screen_corners": ScreenCorners,
        "notification": Notification,
        "launcher": Launcher,
        "activate_linux": ActivateLinux,
        "cheatsheet": Cheatsheet,
    },
)


# Bar configuration
General = TypedDict(
    "General",
    {
        "check_updates": bool,
        "debug": bool,
        "monitor_styles": bool,
        "auto_restart": bool,
        "restart_delay": int,
        "multi_monitor": bool,
        "tooltips": bool,
    },
)

# Cpu configuration
Cpu = TypedDict(
    "Cpu",
    {
        **BaseConfig.__annotations__,
        "mode": Widget_Mode,
        "show_icon": bool,
        "sensor": str,
        "temperature_unit": Temperature_Unit,
        "show_unit": bool,
        "round": bool,
        "graph_length": int,
    },
)

# Mpris configuration
Mpris = TypedDict(
    "Mpris",
    {
        **BaseConfig.__annotations__,
        "truncation_size": int,
        "label_format": str,
        "hide_when_no_player": bool,
        "ignore": list[str],
    },
)

# Memory configuration
Memory = TypedDict(
    "Memory",
    {
        **BaseConfig.__annotations__,
        "mode": Widget_Mode,
        "show_icon": bool,
        "icon": str,
        "graph_length": int,
        "unit": Data_Unit,
    },
)


Gpu = TypedDict(
    "Gpu",
    {
        **BaseConfig.__annotations__,
        "show_icon": bool,
        "icon": str,
        "mode": Widget_Mode,
        "graph_length": int,
    },
)

# Submap configuration
Submap = TypedDict(
    "Submap",
    {
        **BaseConfig.__annotations__,
        "icon": str,
        "show_icon": bool,
        "hide_on_default": bool,
    },
)


# Network configuration
NetworkUsage = TypedDict(
    "NetworkUsage",
    {
        **BaseConfig.__annotations__,
        "label_format": str,
        "upload_threshold": int,
        "download_threshold": int,
        "interval": int,
        "kb_digits": int,
        "mb_digits": int,
    },
)

# Storage configuration
Storage = TypedDict(
    "Storage",
    {
        "mode": Widget_Mode,
        "tooltip": bool,
        "show_icon": bool,
        "icon": str,
        "path": str,
        "graph_length": int,
        "unit": Data_Unit,
    },
)

# Workspaces configuration
Workspaces = TypedDict(
    "Workspaces",
    {
        "count": int,
        "hide_unoccupied": bool,
        "label_format": str,
        "ignored": list[int],
        "icon_map": dict,
        "reverse_scroll": bool,
        "style": str,
        "empty_scroll": bool,
        "show_special": bool,
    },
)

# WindowTitle configuration
WindowTitle = TypedDict(
    "WindowTitle",
    {
        "icon": bool,
        "tooltip": bool,
        "truncation": bool,
        "truncation_size": int,
        "title_map": list[dict[str, str]],
        "fallback": Title_Fallback,
    },
)

# Updates configuration
Updates = TypedDict(
    "Updates",
    {
        **BaseConfig.__annotations__,
        "show_icon": bool,
        "available_icon": str,
        "no_updates_icon": str,
        "hover_reveal": bool,
        "reveal_duration": int,
        "os": str,
        "terminal": str,
        "auto_hide": bool,
        "interval": int,
        "pad_zero": bool,
        "tooltip": bool,
        "label": bool,
        "flatpak": bool,
        "snap": bool,
        "brew": bool,
    },
)


# Bluetooth configuration
BlueTooth = TypedDict("BlueTooth", {**BaseConfig.__annotations__, "icon_size": int})

# Weather configuration
Weather = TypedDict(
    "Weather",
    {
        **BaseConfig.__annotations__,
        "location": str,
        "interval": int,
        "expanded": bool,
        "temperature_unit": Temperature_Unit,
        "wind_speed_unit": Wind_Speed_Unit,
        "label_format": str,
        "hover_reveal": bool,
        "reveal_duration": int,
        "expanded": bool,
        "interval": int,
        "provider": Weather_Provider,
    },
)

Launcher_Button = TypedDict(
    "LauncherButton", {"tooltip": bool, "icon": str, "icon_size": int}
)

# Keyboard configuration
Keyboard = TypedDict(
    "Keyboard", {**BaseConfig.__annotations__, "icon": str, "show_icon": bool}
)

# MicroPhone configuration
MicroPhone = TypedDict("MicroPhone", {**BaseConfig.__annotations__, "show_icon": bool})

# Cava configuration
Cava = TypedDict("Cava", {"bars": int, "color": str})

# Overview configuration
Overview_Button = TypedDict(
    "Overview_Button", {"icon": str, **BaseConfig.__annotations__}
)


ClipBoard = TypedDict(
    "ClipBoard",
    {
        **BaseConfig.__annotations__,
        "icon": str,
        "show_images": bool,
        "item_tooltip": bool,
    },
)

Kanban = TypedDict("kanban", {"icon": str, **BaseConfig.__annotations__})

EmojiPicker = TypedDict(
    "emoji_picker",
    {"icon": str, **BaseConfig.__annotations__, "per_row": int, "per_column": int},
)


# DateTime configuration
DateTimeNotification = TypedDict(
    "DateTimeNotification",
    {
        "enabled": bool,
        "hide_count_on_zero": bool,
        "count": bool,
    },
)

# DateTimeMenu configuration
DateTimeMenu = TypedDict(
    "DateTimeMenu",
    {
        "date_format": str,
        "notification": DateTimeNotification,
        "calendar": bool,
        "hover_reveal": bool,
        "transition_type": str,
        "transition_duration": int,
        "hover_reveal": bool,
        "reveal_duration": int,
    },
)


Custom_Button_Group = TypedDict(
    "Custom_Button_Group",
    {
        "buttons": list[dict[str, str]],
        "spacing": int,
    },
)


Custom_Button = TypedDict(
    "Custom_Button",
    {
        "id": str,
        "command": str,
        "icon": str,
        "label_text": str,
        "tooltip_text": str,
        "show_icon": bool,
        "label": bool,
        "tooltip": bool,
    },
)

# Custom Widget configuration (Waybar-compatible)
CustomWidgetConfig = TypedDict(
    "CustomWidgetConfig",
    {
        "id": str,
        "exec": str,
        "exec_on_event": bool,
        "interval": int,
        "return_type": Return_Type,
        "label_format": str,
        "max_length": int,
        "min_length": int,
        "rotate": int,
        "tooltip": bool,
        "tooltip_format": str,
        "on_click": str,
        "on_click_right": str,
        "on_click_middle": str,
        "on_scroll_up": str,
        "on_scroll_down": str,
        "signal": int,
        "restart_interval": int,
        "format_icons": dict[str, str],
    },
    total=False,
)

# World clock configuration
WorldClock = TypedDict(
    "WorldClock",
    {
        "icon": str,
        "show_icon": bool,
        "timezones": list[str],
        "use_24hr": bool,
    },
)

# ThemeSwitcher configuration
ThemeSwitcher = TypedDict("ThemeSwitcher", {**BaseConfig.__annotations__, "icon": str})

# USB manager configuration
USBManager = TypedDict(
    "USBManager",
    {
        **BaseConfig.__annotations__,
        "icon": str,
        "auto_refresh": bool,
        "refresh_interval": int,
    },
)

# Hyprpicker configuration
HyprPicker = TypedDict(
    "HyprPicker",
    {**BaseConfig.__annotations__, "icon": str, "show_icon": bool, "quiet": bool},
)

# OCR configuration
OCR = TypedDict(
    "OCR", {**BaseConfig.__annotations__, "icon": str, "quiet": bool, "show_icon": bool}
)

Collapsible_Group = TypedDict(
    "Collapsible_Group",
    {
        "widgets": list[str],
        "id": str,
        "spacing": int,
        "icon": str,
        "tooltip": str,
        "style_classes": list[str],
    },
    total=False,
)


Widget_Groups = list[
    TypedDict(
        "WidgetGroup",
        {
            "widgets": list[str],
            "id": str,
            "spacing": int,
            "style_classes": list[str],
            "hover_reveal": bool,
            "reveal_duration": int,
            "revealer_icon": str,
        },
    )
]


# Media configuration
Media = TypedDict(
    "Media",
    {
        "ignore": list[str],
        "truncation_size": int,
        "truncation_size": int,
        "show_album": bool,
        "show_artist": bool,
        "show_player_icon": bool,
        "show_time": bool,
        "show_time_tooltip": bool,
    },
)

# User configuration for QuickSettings
UserConfig = TypedDict(
    "UserConfig",
    {
        "image": str,
        "name": str,
        "distro_icon": bool,
    },
)


ShortCutItem = TypedDict(
    "ShortCutItem",
    {"icon": str, "label": str, "command": str, "tooltip": str, "icon_size": int},
)


ShortcutsConfig = TypedDict("Shortcuts", {"enabled": bool, "items": list[ShortCutItem]})

ControlsConfig = TypedDict(
    "Controls",
    {
        "sliders": list[Slider_Type],
    },
)

# QuickSettings configuration
QuickSettings = TypedDict(
    "QuickSettings",
    {
        "media": Media,
        "hover_reveal": bool,
        "shortcuts": ShortcutsConfig,
        "user": UserConfig,
        "controls": ControlsConfig,
        "toggles": list[str],
    },
)

# Spacing configuration
Spacing = TypedDict("Spacing", {"size": int})

# Divider configuration
Divider = TypedDict("Divider", {"size": int})

# Language configuration
Language = TypedDict(
    "Language", {**BaseConfig.__annotations__, "icon": str, "truncation_size": int}
)

# Volume configuration
Volume = TypedDict("Volume", {**BaseConfig.__annotations__, "step_size": int})

# Brightness configuration
Brightness = TypedDict("Brightness", {**BaseConfig.__annotations__, "step_size": int})


# Recording configuration
Recording = TypedDict(
    "Recording",
    {
        "path": str,
        "delayed": bool,
        "delayed_timeout": int,
        "tooltip": bool,
        "audio": bool,
    },
)

IpMonitor = TypedDict(
    "IpMonitor",
    {**BaseConfig.__annotations__, "label_text": str, "icon": str},
)


Pomodoro = TypedDict(
    "Pomodoro",
    {**BaseConfig.__annotations__, "label_text": str, "icon": str},
)


GitHubTray = TypedDict(
    "GitHubTray",
    {
        **BaseConfig.__annotations__,
        "label_text": str,
        "icon": str,
        "username": str,
        "hostname": str,
        "avatar_size": int,
        "default_tab": str,
        "max_repos": int,
        "sort_by": str,
        "sort_order": str,
        "own_repos_only": bool,
        "cache_ttl": int,
        "notification_interval": int,
        "workflow_runs_max": int,
        "show_notifications": bool,
        "notify_reasons": dict,
        "alerts": dict,
        "local_editor": str,
        "local_projects": dict,
    },
)


# ScreenShot configuration
ScreenShot = TypedDict(
    "ScreenShot",
    {
        "path": str,
        "tooltip": bool,
        "icon_size": int,
        "label": bool,
        "icon": str,
        "annotation": bool,
        "capture_sound": bool,
        "delayed": bool,
        "delayed_timeout": int,
    },
)

# Breathe configuration
Breathe = TypedDict(
    "Breathe",
    {"tooltip": bool, "label": bool, "icon": str},
)


class Widgets(TypedDict):
    """Configuration for all widgets in the bar"""

    battery: Battery
    bluetooth: BlueTooth
    breathe: Breathe
    brightness: Brightness
    cava: Cava
    click_counter: ClickCounter
    cpu: Cpu
    custom_button_group: Custom_Button_Group
    custom_button: Custom_Button
    custom_widget: list[CustomWidgetConfig]
    emoji_picker: EmojiPicker
    kanban: Kanban
    date_time: DateTimeMenu
    divider: Divider
    hypridle: HyprIdle
    hyprsunset: HyprSunset
    hyprpicker: HyprPicker
    launcher_button: Launcher_Button
    keyboard: Keyboard
    language: Language
    gpu: Gpu
    memory: Memory
    microphone: MicroPhone
    mpris: Mpris
    network_usage: NetworkUsage
    ocr: OCR
    ip_monitor: IpMonitor
    pomodoro: Pomodoro
    overview_button: Overview_Button
    wallpaper: WallPaper
    power: PowerButton
    quick_settings: QuickSettings
    recorder: Recording
    screenshot: ScreenShot
    spacing: Spacing
    stopwatch: StopWatch
    storage: Storage
    system_tray: SystemTray
    submap: Submap
    taskbar: TaskBar
    github_tray: GitHubTray
    theme: Theme
    theme_switcher: ThemeSwitcher
    usb_manager: USBManager
    updates: Updates
    volume: Volume
    weather: Weather
    window_title: WindowTitle
    window_count: WindowCount
    workspaces: Workspaces
    world_clock: WorldClock
    clipboard: ClipBoard


class BarConfig(TypedDict):
    """Main configuration that includes all other configurations"""

    widgets: Widgets
    layout: Layout
    modules: Modules
    general: General
    collapsible_group: Collapsible_Group
    widget_groups: Widget_Groups

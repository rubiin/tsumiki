---
title: Widgets Reference
description: Complete configuration reference for all Tsumiki widgets
sidebar:
  order: 1
---

This page documents every widget available in Tsumiki, its configuration options, defaults, and behavior.

Widgets are configured under `[widgets.<name>]` in `config.toml` and placed in the bar via `layout` sections.

## Panel labels

`label_format` is the whole panel label. The widget renders one label and there is no separate `icon` key: the glyph is written directly into `label_format` as a literal character. Any literal text in the string is kept, so the text next to a glyph is part of the format rather than a separate toggle.

A widget whose glyph changes with state — Bluetooth, microphone mute, the update count, the WARP connection — supplies that glyph itself and leads the label with it, so its `label_format` holds only the text you want beside it.

```toml
label_format = "󰌌 {layout}"       # a fixed glyph plus literal text
label_format = "🍅"                # a fixed glyph only
label_format = "Settings"          # text only, no glyph
label_format = ""                  # nothing at all
```

This replaced the old per-widget `show_icon` boolean and the `label` / `label_text` keys, none of which are read any more — a config that still sets `show_icon` logs a warning at startup and falls back to the default.

No widget substitutes an `{icon}` field any more: the glyph is a literal character in `label_format`, and a widget whose glyph changes with state supplies it ahead of the text. Widgets that print live values declare fields for them: `mpris` (`{title}`, `{artist}`, `{album}`, `{name}`), `weather` (`{condition}`, `{temperature}`), `network_usage` (`{upload}`, `{download}`), `window_count` (`{count}`), `workspaces` (`{id}`), `updates` (`{total}`), `hypridle` and `hyprsunset` (`{state}`), `keyboard` (`{layout}`), `language` (`{language}`), `submap` (`{submap}`) and `battery` (`{percent}`, `{time_remaining}`).

Indexed entries follow the same rule: a `[[collapsible_groups]]` toggle button labels itself with `label_format`, with its glyph written straight into the string.

---

## System Information Widgets

### CPU

Displays CPU usage with multiple display modes.

```toml
[widgets.cpu]
label_format = ""
tooltip = true
round = true
temperature_unit = "celsius"
sensor = "acpitz"
mode = "graph"          # "label" | "graph" | "circular"
graph_length = 4
```

- **`mode`**: Display style — `label` shows percentage text, `graph` shows a sparkline, `circular` shows a circular progress ring.
- **`graph_length`**: Number of data points for the sparkline graph.
- **`sensor`**: Thermal zone sensor path (e.g. `acpitz`, `k10temp`). Leave empty for auto-detect.

### Memory

Displays memory usage with multiple display modes.

```toml
[widgets.memory]
label_format = ""
tooltip = true
mode = "label"          # "label" | "graph" | "circular"
graph_length = 4
unit = "gb"             # Display unit for memory values
```

### GPU

Displays GPU usage (supports AMD via `amdgpu` and NVIDIA via `nvidia-smi`).

```toml
[widgets.gpu]
label_format = ""
tooltip = true
mode = "circular"       # "label" | "graph" | "circular"
graph_length = 4
```

### Storage

Displays disk usage for a given path.

```toml
[widgets.storage]
path = "/"
label_format = "󰋊"
mode = "label"          # "label" | "graph" | "circular"
tooltip = true
graph_length = 4
unit = "gb"
```

### Network Usage

Monitors real-time network upload/download speeds.

```toml
[widgets.network_usage]
tooltip = true
label_format = "{upload}   {download} "
upload_threshold = 1024
download_threshold = 1024
kb_digits = 0
mb_digits = 2
interval = 2000         # Polling interval in milliseconds
```

Variables available in `label_format`: `{upload}`, `{download}`.

### Updates

Checks for system package updates (Arch Linux, Flatpak, Snap, Homebrew).

```toml
[widgets.updates]
label_format = "{total}"
pad_zero = true
available_icon = "󰏗"
no_updates_icon = "󰏖"
os = "arch"
interval = 3600         # Refresh interval in seconds
tooltip = true
terminal = "kitty"
auto_hide = false
flatpak = true
snap = false
brew = false
```

- **`label_format`**: Variables available: `{total}` (the update count).
- **`pad_zero`**: Zero-pads `{total}` to two digits (`05`); zero itself stays `0`.
- **`interval`**: Polling interval in seconds (default: 3600 = 1 hour).
- **`os`**: Distribution for native package checking (supports `arch`, `fedora`, `ubuntu`).
- **`flatpak`/`snap`/`brew`**: Enable checking for these package formats.

---

## Hardware & Power Widgets

### Battery

Shows battery level with notifications.

```toml
[widgets.battery]
full_battery_level = 100
hide_percent_when_full = true
hide_when_missing = true
tooltip = true
label_format = "{percent}"

[widgets.battery.notifications]

[widgets.battery.notifications.low_battery]
enabled = false
threshold = 10
message = ""                              # {percent} placeholder supported

[widgets.battery.notifications.full_battery]
enabled = false
message = ""

[widgets.battery.notifications.charging]
enabled = false
message = ""

[widgets.battery.notifications.unplugged]
enabled = false
message = ""
```

Variables available in `label_format`: `{percent}`, `{time_remaining}`. The level glyph leads the label.

#### Notification options

Each notification type is a separate table with the following fields:

| Field       | Types              | Description                                                                                           |
| ----------- | ------------------ | ----------------------------------------------------------------------------------------------------- |
| `enabled`   | all                | Whether to show this notification.                                                                    |
| `threshold` | `low_battery` only | Battery percentage that triggers the low-battery alert (default: `10`).                               |
| `message`   | all                | Custom body text. Supports `{percent}` placeholder. Falls back to the default i18n string when empty. |

**Notification types:**

- **`low_battery`** -- Fires when the battery drops to or below `threshold` while discharging.
- **`full_battery`** -- Fires when the charger is unplugged and the battery is at 100%.
- **`charging`** -- Fires when the charger is plugged in.
- **`unplugged`** -- Fires when the charger is disconnected (and the battery is not full).

### Volume

Controls system audio output volume.

```toml
[widgets.volume]
tooltip = true
step_size = 5
```

Click to toggle mute, scroll to adjust volume.

### Brightness

Controls screen and keyboard brightness.

```toml
[widgets.brightness]
tooltip = true
step_size = 5
```

Requires `brightnessctl`. Click to toggle, scroll to adjust.

### Bluetooth

Manages Bluetooth connections and visibility.

```toml
[widgets.bluetooth]
label_format = ""
tooltip = true
```

Opens a popover to manage paired devices and toggle Bluetooth.

### Microphone

Shows microphone status and muting.

```toml
[widgets.microphone]
tooltip = true
label_format = ""
```

Click to toggle microphone mute.

### Power Button

System power menu with shutdown, reboot, suspend, hibernate, lock, and logout.

```toml
[widgets.power]
tooltip = true
items_per_row = 3
icon_size = 100
label_format = ""
confirm = true

[widgets.power.item_shortcuts]
shutdown = "s"
reboot = "r"
hibernate = "h"
suspend = "u"
lock = "l"
logout = "o"

[widgets.power.buttons]
shutdown = "systemctl poweroff"
reboot = "systemctl reboot"
hibernate = "systemctl hibernate"
suspend = "systemctl suspend"
lock = "loginctl lock-session"
logout = "loginctl terminate-user $USER"
```

- **`confirm`**: Shows a confirmation dialog before executing power actions.
- **`item_shortcuts`**: Keyboard shortcuts for power menu items.

### Hypridle

Toggle Hyprland's idle management daemon.

```toml
[widgets.hypridle]
enabled_icon = ""
label_format = "{state}"
disabled_icon = ""
tooltip = true
```

### Hyprsunset

Toggle blue-light filter (night mode) via Hyprsunset.

```toml
[widgets.hyprsunset]
temperature = "2800k"
enabled_icon = "󱩌"
label_format = "{state}"
disabled_icon = "󰛨"
tooltip = true
```

### Hyprpicker

Color picker that captures a color from the screen.

```toml
[widgets.hyprpicker]
tooltip = true
quiet = false
label_format = ""
```

The selected color is copied to clipboard. In quiet mode, no notification is shown.

---

## Desktop & Workspace Widgets

### Workspaces

Displays virtual desktops with click/scroll switching. See the [full Workspaces documentation](/en/features/workspaces) for details.

```toml
[widgets.workspaces]
count = 10
hide_unoccupied = true
ignored = [-99]
reverse_scroll = false
style = "numbered"       # "numbered" | "pill" | "icon" | "default" | "underline" | "bubble"
empty_scroll = false
label_format = "{id}"
icon_map = {}
show_special = false
show_urgent = false
```

- **`style`**: Choose from `numbered`, `pill`, `icon`, `default`, `underline`, or `bubble`.
- **`icon_map`**: Map workspace IDs to custom icons: `{ "1": "", "2": "" }`.
- **`label_format`**: Format string with `{id}` variable.
- **`show_special`**: Show special workspaces (negative IDs). Set to `false` to hide them.
- **`show_urgent`**: Show pulse animation and color on workspaces with urgent windows. Set to `true` to enable.

### Window Title

Shows the title of the currently focused window.

```toml
[widgets.window_title]
icon = true
truncation = true
truncation_size = 50
tooltip = true
mappings = true
title_map = []
fallback = "class"       # "class" | "title"
```

- **`title_map`**: List of mapping rules to rename window titles.
- **`fallback`**: What to show when no title is available.

### Window Count

Shows the number of windows in the current workspace.

```toml
[widgets.window_count]
label_format = " [{count}]"
hide_when_zero = true
tooltip = true
```

Variables available in `label_format`: `{count}`.

### Overview Button

Button that opens the window overview/exposé.

```toml
[widgets.overview_button]
label_format = ""
tooltip = true
```

### Taskbar

Shows running applications as clickable icons similar to a traditional taskbar.

```toml
[widgets.taskbar]
icon_size = 22
ignored = []
tooltip = true
show_current_workspace_only = false
```

---

## Date, Time & Calendar

### Date & Time Menu

Shows the current date/time with a calendar popover and event notifications.

```toml
[widgets.date_time]
date_format = " %a %b %d,"
calendar = true
clock_format = "12h"   # "12h" | "24h"
hover_reveal = false
reveal_duration = 500

[widgets.date_time.notification]
enabled = true
count = true
hide_count_on_zero = true
```

### World Clock

Shows time in multiple timezones.

```toml
[widgets.world_clock]
use_24hr = true
label_format = "󱉊"
timezones = ["America/New_York", "Asia/Tokyo"]
```

---

## Media & Audio Widgets

### MPRIS Media Controls

Displays currently playing media with playback controls.

```toml
[widgets.mpris]
truncation_size = 20
tooltip = true
label_format = "{title} - {artist}"
hide_when_no_player = true
ignore = []
```

Variables available in `label_format`: `{title}`, `{artist}`, `{album}`, `{name}`.

Requires `playerctl`. Automatically hides when no media player is running.

### Cava Audio Visualizer

Real-time audio visualization powered by Cava.

```toml
[widgets.cava]
bars = 10
color = "#89b4fa"
```

Requires Cava to be installed and configured.

---

## System Utilities

### Screenshot

Capture screenshots with annotation support.

```toml
[widgets.screenshot]
path = "Pictures/Screenshots"
label_format = ""
tooltip = true
annotation = true
delayed = false
delayed_timeout = 5000
capture_sound = false
```

Uses `grimblast` for captures and `satty` for annotations.

### Screen Recording

Start/stop screen recording with optional audio.

```toml
[widgets.recorder]
path = "Videos/Screencasting"
tooltip = true
audio = true
delayed = false
delayed_timeout = 5000
```

Uses `wf-recorder` for recording.

### OCR (Optical Character Recognition)

Extract text from a screen region using Tesseract.

```toml
[widgets.ocr]
tooltip = true
label_format = ""
quiet = false
```

Requires `tesseract`, `slurp`, and `imagemagick`.

### Clipboard Manager

Clipboard history manager with image support.

```toml
[widgets.clipboard]
label_format = ""
tooltip = true
item_tooltip = false
show_images = true
enable_pinning = true
```

Uses `cliphist` for clipboard history.

### USB Manager

Manage USB drive mounting and ejection.

```toml
[widgets.usb_manager]
label_format = ""
tooltip = true
```

---

## Input & Language Widgets

### Keyboard Layout

Displays the current keyboard layout.

```toml
[widgets.keyboard]
tooltip = true
label_format = "󰌌 {layout}"
```

### Language

Shows the current input language.

```toml
[widgets.language]
tooltip = true
truncation_size = 2
label_format = ""
```

### Submap

Displays the active Hyprland keybind submap.

```toml
[widgets.submap]
tooltip = true
label_format = "󰌌 {submap}"
hide_on_default = false
```

Hides automatically when the active submap is the default.

---

## UI & Application Widgets

### Launcher Button

Opens the application launcher popup.

```toml
[widgets.launcher_button]
icon = "view-app-grid-symbolic"
icon_size = 20
tooltip = true
```

### Quick Settings

A comprehensive quick settings panel with user info, controls, media, and shortcuts.

The `toggles` array selects which quick settings buttons appear. Available
toggles: wifi, bluetooth, power_profiles, hyprsunset, hypridle, notification,
darkmode, flightmode. They flow two per row; an empty array hides the toggle
section entirely. darkmode and flightmode are opt-in and not enabled by default.

```toml
[widgets.quick_settings]
hover_reveal = false
toggles = ["wifi", "bluetooth", "power_profiles", "hyprsunset", "hypridle", "notification"]

[widgets.quick_settings.user]
avatar = "~/.face"
name = "system"
distro_icon = true

[widgets.quick_settings.controls]
sliders = ["brightness", "volume"]

[widgets.quick_settings.media]
enabled = true
ignore = []
truncation_size = 30
show_album = true
show_artist = true
show_player_icon = true
show_time = true
show_time_tooltip = true

[widgets.quick_settings.shortcuts]
enabled = true

[[widgets.quick_settings.shortcuts.items]]
icon = ""
label = "Terminal"
command = "kitty"
tooltip = "Open terminal"
icon_size = 18
```

### System Tray

System tray for background applications (NetworkManager, Bluetooth, etc.).

```toml
[widgets.system_tray]
icon_size = 16
ignored = []
hidden = []
hide_when_empty = false
```

### Wallpaper Button

Opens the wallpaper selection popup.

```toml
[widgets.wallpaper]
label_format = ""
tooltip = true
```

### Settings Button

Opens the in-app settings GUI.

```toml
[widgets.settings]
label_format = "󰒓"
tooltip = true
```

### Theme Switcher

Quickly switch between installed themes.

```toml
[widgets.theme_switcher]
icon = ""
notify = false    # Show notification on theme change
```

### Cheatsheet

Displays a searchable keybind cheatsheet for Hyprland.

```toml
[widgets.cheatsheet]
label_format = "󰌌"              # the fixed glyph; "" for no label at all
tooltip = true
title = "Hyprland Cheatsheet"
columns = 3
groups_per_page = 6
max_entries_per_group = 8
```

### Emoji Picker

Search and insert emoji characters.

```toml
[widgets.emoji_picker]
label_format = ""
tooltip = true
per_row = 9
per_column = 4
```

### Kanban Board

A simple Kanban task management board.

```toml
[widgets.kanban]
label_format = "󱞁"
tooltip = true
```

### Pomodoro Timer

A Pomodoro productivity timer.

```toml
[widgets.pomodoro]
label_format = "🍅"
tooltip = true
```

### GitHub Tray

Account-wide GitHub tray: unread notifications, repositories, and per-repository
issues, pull requests and Actions runs — plus desktop alerts for new stars,
followers and workflow results.

Every API call goes through the `gh` CLI, so install and authenticate it first:

```bash
gh auth login
```

```toml
[widgets.github_tray]
label_format = ""
tooltip = true
# Optional login used as a fallback while the gh session user is resolved.
username = ""
# GitHub Enterprise Server host (must be added to gh), empty = github.com
hostname = ""
avatar_size = 44
default_tab = "inbox"       # "inbox" | "repos"
max_repos = 10
sort_by = "updated"        # "updated" | "pushed" | "created" | "stars" | "name"
sort_order = "desc"
own_repos_only = false     # only show repos owned by your account (hide org/collaborator)
# Seconds profile and repository data stay cached before a refetch (0 disables).
cache_ttl = 3600
notification_interval = 60 # seconds between unread refreshes
workflow_runs_max = 10
show_notifications = true
# Editor used to open locally-mapped repositories.
local_editor = "code"
# Map owner/repository to a local folder to open it in your editor from the tray.
local_projects = { "owner/repository" = "~/code/repository" }

[widgets.github_tray.notify_reasons]
review_requests = true
mentions = true
assignments = true
pr_comments = true
issue_comments = true

[widgets.github_tray.alerts]
enabled = true
new_stars = true
new_forks = true
new_issues = true
new_followers = true
new_notifications = true
workflow_started = true
workflow_success = true
workflow_failure = true
workflow_cancelled = true
```

### Cloudflare WARP

Manage Cloudflare WARP VPN connection — connect, disconnect, and view status.

```toml
[widgets.cloudflare_warp]
label_format = ""
tooltip = true
connected_icon = ""
disconnected_icon = ""
```

- **connected_icon** / **disconnected_icon**: Nerd Font icons shown in the bar for each state.
- Click the widget to open a popover with a toggle button.
- Requires `warp-cli` from [Cloudflare WARP Client for Linux](https://developers.cloudflare.com/warp-client/get-started/linux/).
- The service polls `warp-cli status` every 5 seconds to detect state changes.

### DNS Switcher

Quickly switch between popular DNS providers directly from the bar.

```toml
[widgets.dns_switcher]
label_format = "󰚘"
tooltip = true
```

Click to open a popover with pre-configured providers:

| Provider   | Primary DNS      | Secondary DNS     |
| ---------- | ---------------- | ----------------- |
| Cloudflare | `1.1.1.1`        | `1.0.0.1`         |
| Google     | `8.8.8.8`        | `8.8.4.4`         |
| OpenDNS    | `208.67.222.222` | `208.67.220.220`  |
| AdGuard    | `94.140.14.14`   | `94.140.15.15`    |
| Quad9      | `9.9.9.9`        | `149.112.112.112` |

Includes a "Reset to Default (ISP)" button to restore automatic DNS.

- Uses `nmcli` (NetworkManager) to manage DNS settings.
- DNS changes require Polkit authentication (`pkexec`).
- The service polls `nmcli` every 3 seconds to detect the current DNS server.

### IP Monitor

Displays the current IP address.

```toml
[widgets.ip_monitor]
label_format = "󰖟"
tooltip = true
```

### Stopwatch

A simple stopwatch/timer.

```toml
[widgets.stopwatch]
stopped_icon = "󱫞"
running_icon = "󱫠"
```

### Click Counter

A counter that increments on each click.

```toml
[widgets.click_counter]
count = 0
```

### Breathe

A breathing exercise guide widget.

```toml
[widgets.breathe]
icon = ""
tooltip = true
```

### Weather

Displays current weather conditions for a location.

```toml
[widgets.weather]
location = "kathmandu"
label_format = "{temperature} {condition}"
tooltip = true
expanded = true
temperature_unit = "celsius"   # "celsius" | "fahrenheit"
wind_speed_unit = "kmh"        # "kmh" | "mph" | "ms" | "beaufort"
interval = 86400
hover_reveal = true
reveal_duration = 500
provider = "open-meteo"        # "open-meteo" | "wttr"
```

Variables available in `label_format`: `{temperature}`, `{condition}`.

---

## Layout & Grouping Widgets

### Divider

A visual separator between bar sections.

```toml
[widgets.divider]
size = 2
```

For advanced configuration, see [Advanced Configuration](/en/configuring/advanced) for configuration and usage.

---
title: Modules Reference
description: Complete documentation for all Tsumiki modules
sidebar:
  order: 2
---

Modules are larger UI surfaces beyond the bar, such as the dock, notifications, overview, and OSD. They are configured under `[modules.<name>]` in `config.toml`.

Unlike widgets, most modules are standalone windows or overlays that need to be explicitly enabled.

---

## Bar

The bar itself is a module. Configures position, layer, auto-hide behavior.

```toml
[modules.bar]
layer = "top"           # "top" | "overlay" | "bottom" | "background"
auto_hide = false
auto_hide_timeout = 3000   # milliseconds
location = "top"           # "top" | "bottom"
```

- **`layer`**: Hyprland layer — `top` renders above windows, `background` renders below.
- **`auto_hide`**: Hides the bar after the timeout when not hovered.
- **`location`**: Bar position on screen.

---

## Notification System

Displays desktop notifications as they arrive, with stacking, grouping, and Do Not Disturb.

```toml
[modules.notification]
enabled = true
anchor = "top-right"
auto_dismiss = true
respect_expire = true
dnd_on_screencast = true
ignored = []
transition_type = "slide-left"       # "slide-left" | "slide-right" | "slide-up" | "slide-down" | "crossfade"
transition_duration = 350
per_app_limits = {}
play_sound = false
max_actions = 3
copy_code_action = true
show_timestamp = true
dismiss_on_hover = false
sound_file = "notification4"
max_lines = 4
max_expanded_lines = 20

[modules.notification.timeout]
low = 3000
normal = 8000
critical = 15000

[modules.notification.persist]
enabled = true
low = true
normal = true
critical = true
max_count = 200
```

- **`anchor`**: Screen position for the notification window.
- **`auto_dismiss`**: Automatically dismiss notifications after their timeout.
- **`respect_expire`**: Whether to respect the expire timeout from the notification sender.
- **`dnd_on_screencast`**: Enables Do Not Disturb mode during screen recording.
- **`per_app_limits`**: Limit notifications per application: `{ "app_name": 5 }`.
- **`copy_code_action`**: Detects one-time (2FA) codes in the body and shows a `Copy "123456"` action that copies the code to the clipboard and dismisses the notification.
- **`show_timestamp`**: Shows a relative timestamp (e.g. `5m ago`) in the notification header.
- **`persist`**: Save notifications to disk for recall after restart.

---

## Dock

A pinned-application launcher with intellihide, window previews, and app grouping.

```toml
[modules.dock]
enabled = false
ignored = []
icon_size = 40
behavior = "intellihide"            # "intellihide" | "always_show"
tooltip = false
layer = "top"
show_when_no_windows = false
group_apps = true
truncation_size = 20
orientation = "horizontal"
always_show_focused = true
hide_special_workspace_apps = false
show_launcher = true
launcher_position = "last"          # "first" | "last"
ignored = []
```

- **`behavior`**: `intellihide` hides the dock when a window overlaps it; `always_show` keeps it visible.
- **`s`**: Shows window preview thumbnails on hover.
- **`group_apps`**: Groups multiple windows from the same application.
- **`show_launcher`**: Adds an application launcher icon to the dock.
- **`hide_special_workspace_apps`**: Hides apps on special workspaces (scratchpads).

### Keybindings

Navigate the dock with:

| Action                   | Keybinding                        |
| ------------------------ | --------------------------------- |
| Focus next client        | `Super+Tab`                       |
| Focus previous client    | `Super+Shift+Tab`                 |
| Open launcher            | `Super+Space`                     |
| Move client to workspace | Right-click → "Move to Workspace" |

---

## Overview (Workspace Exposé)

Full-screen overview of all workspaces and their windows.

```toml
[modules.overview]
enabled = false
layer = "top"
anchor = "center"
transition_type = "crossfade"       # "crossfade" | "slide-left" | "slide-right" | "slide-up" | "slide-down"
transition_duration = 350
```

Opens with a configurable keybinding (default: `Super+W`). Shows workspace thumbnails with click-to-focus.

---

## Launcher

Keyboard-driven application launcher with search, grid/list layout, and drag-to-pin.

```toml
[modules.launcher]
enabled = false
tooltip = true
icon_size = 35
ignored = []
anchor = "center"
width = 280
height = 320
layout = "grid"                    # "grid" | "list"
grid_columns = 3
plugins_enabled = true              # slash-command plugins (/calc, /translate)
plugins_dir = ""                    # default: <config>/plugins
plugins = ["calc", "emoji"]          # allowlist of plugins to load (empty = none)
```

- **`layout`**: `grid` shows app icons in a grid; `list` shows them as a list with names.
- **`anchor`**: Position on screen (`center`, `top`, `bottom`, etc.).
- **`ignored`**: List of desktop file names to exclude from search results.
- **`plugins_enabled`**: Enables slash-command plugins (`/calc`, `/translate`, ...).
- **`plugins_dir`**: Directory containing Python plugins; defaults to `<config>/plugins`.
- **`plugins`**: Strict allowlist of plugin names to load (e.g. `["calc", "emoji"]`).
  An empty list loads **no** plugins — list every plugin you want to use.
  Names are matched case-insensitively against the plugin's `name` (the slash
  command), **not** its aliases.

### Keybindings

| Action        | Keybinding    |
| ------------- | ------------- |
| Open launcher | `Super+Space` |
| Navigate      | Arrow keys    |
| Launch app    | `Enter`       |
| Close         | `Escape`      |

### Slash Commands & Plugins

Type `/` in the search box to browse the available slash commands, or use one
straight away, e.g. `/calc 2+2` or `/translate bonjour`. Only plugins listed
under `plugins` in `[modules.launcher]` are loaded — an empty list means no
slash commands are available. Plugins are written in Python — drop a `.py`
file (or a package directory) into `plugins/`, add its name to `plugins`,
and restart the bar.

Bundled plugins:

- **`/calc`** — math, units and currency via libqalculate (`qalc`), e.g.
  `/calc 100 cm to inches`.
- **`/translate`** — translation with auto-detected source language, e.g.
  `/translate bonjour`.
- **`/emoji`** — offline emoji search, e.g. `/emoji rocket`.
- **`/clipboard-history`** — search `cliphist` history and copy an item back,
  e.g. `/clipboard-history https://`.
- **`/currency`** — convert between currencies with live rates (Frankfurter,
  no API key), e.g. `/currency 100 usd to eur`.
- **`/kill`** — search running processes and kill the selected one
  (SIGTERM, or SIGKILL with `-9`), e.g. `/kill firefox`. A numeric query is
  treated as a port — `/kill 3000` kills whatever is listening on port 3000.
- **`/search`** — search the web (DuckDuckGo, no API key) and open a result
  in your browser while copying its URL to the clipboard, e.g.
  `/search fabric hyprland`.
- **`/history`** — search your shell command history (bash, zsh, fish) and
  copy a command back to the clipboard, e.g. `/history git`. Nothing is ever
  executed.
- **`/define`** — look up a word on dict.org's WordNet (DICT protocol, no API
  key), e.g. `/define serendipity`; pick another database with
  `/define -d foldoc monad`.
- **`/shorten`** — shorten a URL via is.gd (TinyURL fallback), e.g.
  `/shorten github.com/rubiin/tsumiki` — Enter copies the short link.
- **`/unicode`** — search and copy Unicode characters by name, e.g.
  `/unicode arrow` or `/unicode copyright`.

Keyboard: `Up`/`Down` move the selection, `Enter` activates the highlighted
row, `Escape` closes.

#### Writing a plugin

Each plugin subclasses `LauncherPlugin`:

```python
# plugins/hello.py
from utils.plugin_manager import LauncherPlugin, PluginResult, copy_to_clipboard


class HelloPlugin(LauncherPlugin):
    name = "hello"  # slash command: /hello
    description = "Say hello"
    icon = "face-smile-symbolic"
    aliases = ["hi"]

    def handle(self, args):
        # Runs on a worker thread - no GTK calls allowed here.
        who = args.strip() or "world"
        return [PluginResult(f"Hello, {who}!", subtitle="Press Enter to copy")]

    def execute(self, result):
        if result:
            copy_to_clipboard(result.title)
        return False  # False closes the launcher
```

- `name` is the slash command; `aliases` registers additional names.
- `handle(args)` returns the rows shown live while you type.
- `execute(result)` runs when a row is activated (Enter/click); return `True`
  to keep the launcher open.
- `handle()` runs on a worker thread — keep it free of GTK calls. Broken
  plugins are skipped with a warning and never crash the bar.
- For multi-file plugins, use a package (a directory with `__init__.py`) and
  re-export the plugin class from `__init__.py`.

For the full plugin API — class attributes, helpers, cancellation,
debouncing, and package layout — see the [Plugin Development guide](/en/resources/plugins).

---

## OSD (On-Screen Display)

Transient overlays for volume, brightness, and other adjustments.

```toml
[modules.osd]
enabled = false
timeout = 3000
anchor = "bottom-center"
orientation = "horizontal"
percentage = true
icon_size = 25
play_sound = false
transition_type = "slide-up"       # "slide-up" | "slide-down" | "slide-left" | "slide-right" | "crossfade"
transition_duration = 500
osds = ["brightness", "volume"]
```

- **`osds`**: Which OSD types to show. Available: `brightness`, `volume`, `microphone`, `lockkeys`.
- **`percentage`**: Shows a percentage indicator alongside the icon.
- **`play_sound`**: Plays a sound when the OSD appears.

---

## Desktop Clock

A decorative clock overlay on the desktop (layer bottom).

```toml
[modules.desktop_clock]
enabled = false
type = "cookie"                    # Clock widget type
layer = "bottom"
anchor = "bottom-right"
date_format = "%A, %d %B %Y"
time_format = "%H:%M"
nepali_date = false
cookie_size = 230
cookie_sides = 9
cookie_dial_style = "dots"
cookie_hour_hand_style = "fill"
cookie_minute_hand_style = "medium"
cookie_second_hand_style = "dot"
cookie_date_style = "bubble"
cookie_show_seconds = false
cookie_show_hour_marks = false
cookie_background_opacity = 1.0
cookie_widget_scale = 1.0
```

The `cookie_*` options configure the visual style of the analog clock widget.

---

## Desktop Quotes

Displays rotating inspirational quotes on the desktop.

```toml
[modules.desktop_quotes]
enabled = false
anchor = "bottom-right"
layer = "bottom"
interval = 600      # Seconds between quote rotations
```

Quotes are fetched from an external API.

---

## Activate Linux

Shows a window activation hint overlay (similar to GNOME's window overview on Alt+Tab).

```toml
[modules.activate_linux]
enabled = false
anchor = "bottom-right"
layer = "bottom"
```

---

## Screen Corners

Adds hot corners to the screen edges.

```toml
[modules.screen_corners]
enabled = false
size = 20
```

---

## Cheatsheet

A searchable Hyprland keybinding cheatsheet.

Configured under `[widgets.cheatsheet]` — see the [Widgets Reference](/en/features/widgets) for details.

---

## Settings GUI

An in-app GUI for editing Tsumiki configuration.

Triggered from the Settings widget (`[widgets.settings]`). No module-level configuration needed.

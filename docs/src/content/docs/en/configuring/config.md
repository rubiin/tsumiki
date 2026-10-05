---
title: Configuration
description: Tsumiki configuration options and widget settings
---

Tsumiki uses TOML for configuration.

## Config Files

- `config.toml`: widgets, layout, modules, runtime behavior.
- `tsumiki.schema.json`: schema source of truth.

:::note
The schema requires top-level `widget_groups` and `collapsible_groups` sections.
Starting from `example/config.toml` is the safest way to stay schema-valid.
:::

## Quick Start Example

```toml
"$schema" = "./tsumiki.schema.json"

[general]
debug = false
auto_restart = true
multi_monitor = false

[layout]
left_section = ["workspaces", "window_title"]
middle_section = ["date_time"]
right_section = ["@group:0", "system_tray", "volume", "battery"]

[[widget_groups]]
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]

[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
tooltip = "Utility Tools"
style_classes = ["utility-tools"]

[modules.bar]
layer = "top"
location = "top"
auto_hide = false
auto_hide_timeout = 3000

[widgets.workspaces]
count = 10
hide_unoccupied = true

[widgets.date_time]
date_format = "%b %d %H:%M"

[widgets.volume]
tooltip = true
step_size = 5

[widgets.battery]
label = true
tooltip = true
```

## Main Sections

### `general`

Global behavior such as debug mode, auto reload, and multi-monitor controls.

| Key              | Type | Default | Description                    |
| ---------------- | ---- | ------- | ------------------------------ |
| `debug`          | bool | `false` | Enable verbose logging         |
| `auto_restart`   | bool | `true`  | Automatically restart on crash |
| `restart_delay`  | int  | `1500`  | Delay before restart (ms)      |
| `multi_monitor`  | bool | `false` | Per-monitor bar instances      |
| `tooltips`       | bool | `true`  | Enable widget tooltips         |
| `check_updates`  | bool | `false` | Check for Tsumiki updates      |
| `monitor_styles` | bool | `true`  | Watch and reload SCSS changes  |

### `layout`

Controls widget placement in bar sections:

- `left_section`
- `middle_section`
- `right_section`

Each value is a list of widget IDs. Use `@group:N` (zero-based index) for widget groups:

```toml
[layout]
left_section = ["@group:0", "window_title"]
middle_section = ["date_time"]
right_section = ["@group:1", "system_tray", "power"]
```

Available reference types:

| Reference                                | Example                                             | Description                             |
| ---------------------------------------- | --------------------------------------------------- | --------------------------------------- |
| Widget name                              | `"workspaces"`                                      | Direct widget reference                 |
| `@group:N` / `@group:id`                 | `"@group:0"` / `"@group:workspaces-group"`          | Widget group by index or string id      |
| `@collapsible:N` / `@collapsible:id`     | `"@collapsible:0"` / `"@collapsible:utility-tools"` | Collapsible group by index or string id |
| `@custom_widget:N` / `@custom_widget:id` | `"@custom_widget:0"` / `"@custom_widget:volume"`    | Custom widget by index or string id     |

### `modules`

Enables and configures larger UI modules such as:

| Module         | Key                      | Description                                                         |
| -------------- | ------------------------ | ------------------------------------------------------------------- |
| Bar            | `modules.bar`            | Panel bar position and layer                                        |
| Notification   | `modules.notification`   | Desktop notification system                                         |
| Dock           | `modules.dock`           | Application dock with intellihide                                   |
| Overview       | `modules.overview`       | Workspace exposé view                                               |
| OSD            | `modules.osd`            | On-screen display for volume, etc.                                  |
| Launcher       | `modules.launcher`       | Application search & launch, slash commands (`/calc`, `/translate`) |
| Desktop Clock  | `modules.desktop_clock`  | Decorative desktop clock                                            |
| Desktop Quotes | `modules.desktop_quotes` | Inspirational quote overlay                                         |
| Screen Corners | `modules.screen_corners` | Hot corners                                                         |
| Cheatsheet     | `modules.cheatsheet`     | Keybinding reference                                                |
| Activate Linux | `modules.activate_linux` | Window activation hint                                              |

Example dock configuration:

```toml
[modules.dock]
enabled = true
behavior = "intellihide"
show_when_no_windows = false
icon_size = 40
```

See the [Modules Reference](/en/features/modules) for complete options.

### `widgets`

Per-widget settings (icons, labels, thresholds, polling intervals, behavior flags).

Over 45 widgets are available. See the complete [Widgets Reference](/en/features/widgets) for every option.

Common widgets include:

| Widget           | Description                 |
| ---------------- | --------------------------- |
| `workspaces`     | Virtual desktop switcher    |
| `window_title`   | Active window title         |
| `date_time`      | Date/time display           |
| `system_tray`    | System tray icons           |
| `volume`         | Audio volume control        |
| `battery`        | Battery status              |
| `cpu`            | CPU usage monitor           |
| `memory`         | Memory usage monitor        |
| `network_usage`  | Network speed monitor       |
| `weather`        | Weather conditions          |
| `power`          | Power menu (shutdown, etc.) |
| `quick_settings` | Quick settings panel        |

## Workspace Styles

The workspace widget supports six display styles:

```toml
[widgets.workspaces]
style = "numbered"   # "numbered" | "pill" | "icon" | "minimal" | "underline" | "bubble"
```

- **numbered** — Numbers with pill-shaped active indicator (default)
- **pill** — Minimal pill indicators without text
- **icon** — Custom Nerd Font icons per workspace
- **minimal** — Clean, understated with subtle background
- **underline** — Active workspace gets a bottom border accent, no background
- **bubble** — Circular bubble containers

See the [Workspaces Widget](/en/features/workspaces) page for full details.

## Widget Groups & Collapsible Groups

Group widgets together with shared spacing and styling:

```toml
[[widget_groups]]
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

Groups can optionally use a hover-revealer that hides children until hovered:

```toml
[[widget_groups]]
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
hover_reveal = true
reveal_duration = 300
revealer_icon = "󰍽"
```

| Key               | Type   | Default | Description                                           |
| ----------------- | ------ | ------- | ----------------------------------------------------- |
| `hover_reveal`    | bool   | `false` | Hide children behind a revealer that expands on hover |
| `reveal_duration` | int    | `500`   | Transition duration in milliseconds                   |
| `revealer_icon`   | string | `󰍽`     | Nerd Font icon shown when the group is collapsed      |

Collapsible groups hide widgets behind a toggle:

```toml
[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
label_format = "{icon}"
tooltip = "Utility Tools"
style_classes = ["utility-tools"]
```

The toggle button is one label, driven by `label_format` like every other panel widget. `{icon}` is the only field here: literal text in the string is kept, so `"{icon} Tools"` puts a caption next to the glyph. The old `show_icon` / `label` keys are no longer read.

Reference groups in layout with `@group:N` (numeric index) or `@group:id` (string id).

Each group entry can include an optional `id` field for human-readable references:

```toml
[[widget_groups]]
id = "workspaces-group"
widgets = ["workspaces", "window_title"]
spacing = 2
style_classes = ["compact"]

[[collapsible_groups]]
id = "utility-tools"
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
label_format = "{icon}"
tooltip = "Utility Tools"
style_classes = ["utility-tools"]

[layout]
left_section = ["@group:workspaces-group"]
right_section = ["@collapsible:utility-tools"]
```

## Matugen Theme Generation

Auto-generate color palettes from your wallpaper:

```toml
[matugen]
enabled = true
wallpaper = "~/Pictures/wallpaper.jpg"
scheme = "scheme-tonal-spot"
mode = "dark"
contrast = 0.0
```

See [Theming with Matugen](/en/theming/matugen) for details.

## Recommended Workflow

1. Start from `example/config.toml`.
2. Keep your custom file small and focused.
3. Change one section at a time.
4. Restart with `./tsumiki.sh -start` to validate behavior.

## Reference Source

This page is a practical overview.
For complete key definitions and defaults, see the [Widgets Reference](/en/features/widgets) and [Modules Reference](/en/features/modules).
For the complete schema, use `tsumiki.schema.json` in the project root.

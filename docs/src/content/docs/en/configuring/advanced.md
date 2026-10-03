---
title: Advanced Configuration
description: Advanced Tsumiki configuration patterns
---

Once you are comfortable with the [Configuration](/en/configuring/config) basics, these patterns help you tune Tsumiki further.

## Custom Widget

Waybar-compatible custom widgets that run external shell commands with configurable output parsing and click handling.

```toml
[[widgets.custom_widget]]
id = "volume"
exec = "pamixer --get-volume"
format = "󰕾 {}%"
interval = 1
on_scroll_up = "pamixer -i 5"
on_scroll_down = "pamixer -d 5"
exec_on_event = true

[layout]
left_section = ["@custom_widget:volume", "workspaces"]
```

Full configuration options:

| Key                | Type   | Default   | Description                                                          |
| ------------------ | ------ | --------- | -------------------------------------------------------------------- |
| `id`               | string | —         | Unique identifier for referencing in layout (`@custom_widget:my-id`) |
| `exec`             | string | required  | Shell command to execute                                             |
| `interval`         | int    | `0`       | Refresh interval in seconds (0 = run once)                           |
| `return_type`      | string | `"plain"` | Output format: `"plain"` or `"json"`                                 |
| `label_format`     | string | `"{}"`    | Format string where `{}` is replaced with output                     |
| `exec_on_event`    | bool   | `false`   | Re-run command after click/scroll                                    |
| `max_length`       | int    | `0`       | Max text length (0 = no limit)                                       |
| `min_length`       | int    | `0`       | Min text length (pads with spaces)                                   |
| `rotate`           | int    | `0`       | Rotate text by degrees                                               |
| `tooltip`          | bool   | `true`    | Show tooltip with output                                             |
| `tooltip_format`   | string | —         | Tooltip format string                                                |
| `on_click`         | string | —         | Left-click command                                                   |
| `on_click_right`   | string | —         | Right-click command                                                  |
| `on_click_middle`  | string | —         | Middle-click command                                                 |
| `on_scroll_up`     | string | —         | Scroll-up command                                                    |
| `on_scroll_down`   | string | —         | Scroll-down command                                                  |
| `signal`           | int    | —         | Signal number for sig* event triggers                                |
| `restart_interval` | int    | —         | Restart interval for persistent scripts                              |

## Widget Groups

Group widgets together with shared spacing and style:
Reference a group in your layout with `@group:N` (zero-based index) or `@group:id` (string id):

```toml
[[widget_groups]]
id = "sys-group"
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

Reference in layout with `@group:sys-group`.

```toml
[layout]
right_section = ["@group:sys-group", "system_tray"]
```

### Hover Reveal

Add `hover_reveal = true` to hide the group children behind a revealer that slides open on hover. An optional `revealer_icon` is displayed while collapsed.

```toml
[[widget_groups]]
id = "sys-group"
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
hover_reveal = true
reveal_duration = 300
revealer_icon = "󰍽"
```

## Collapsible Groups

Hide less-used widgets behind a toggle:

```toml
[[collapsible_groups]]
id = "utility-tools"
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
tooltip = "Utility Tools"
style_classes = ["utility-tools"]
```

Reference in layout with `@collapsible:utility-tools`.

```toml

right_section = ["@collapsible:utility-tools", "system_tray"]

```

## Custom Buttons

Custom command buttons. Each button is referenced via `@custom_button:id` or `@custom_button:N`. Place several in a [widget group](#widget-groups) when you want shared spacing and styling.

```toml
[[widgets.custom_buttons]]
id = "firefox"
command = "firefox"
icon = "󰈹"
label_text = "Firefox"
tooltip_text = "Open Firefox Browser"
label_format = "{icon}"
label = false
tooltip = true

[layout]
left_section = ["@custom_button:firefox"]
```

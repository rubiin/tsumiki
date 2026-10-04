---
title: Migrating from v2 to v3
description: Step-by-step guide for upgrading your Tsumiki configuration from v2 to v3.
sidebar:
  order: 2
---

import { Steps } from "@astrojs/starlight/components";

This guide covers the main breaking changes between v2 and v3 and how to migrate safely.

---

## Overview of breaking changes

| Area                | Change                                                         |
| ------------------- | -------------------------------------------------------------- |
| Config format       | JSON5 no longer supported — use TOML                           |
| Power profile       | `power_profile` option removed from `general`                  |
| Dock config         | Dock settings live under `[modules.dock]`                      |
| Bar auto-hide       | Bar auto-hide is configured under `[modules.bar]`              |
| Group sections      | Use top-level `[[widget_groups]]` and `[[collapsible_groups]]` |
| `all_visible` param | Removed from widget constructors                               |

---

## Step-by-step migration

<Steps>

### 1. Convert your config file format

JSON5 is no longer supported. Use TOML.

**Before (v2):** `~/.config/tsumiki/config.json5`

**After (v3):** `~/.config/tsumiki/config.toml`

Fastest path is to copy the latest example and re-apply your custom values:

```sh
cp ~/.config/tsumiki/example/config.toml ~/.config/tsumiki/config.toml
```

### 2. Remove `power_profile` from general settings

The `power_profile` key is no longer used. Remove it from `[general]`.

```toml
[general]
# remove this key if present
# power_profile = "balanced"
```

### 3. Update dock configuration

Dock options are configured under `[modules.dock]`.

```toml
# Before (v2)
[modules.dock]
show_when_no_windows = true
icon_size = 28
behavior = "intellihide"

# After (v3)
[modules.dock]
icon_size = 28
show_when_no_windows = true
behavior = "intellihide"
```

### 4. Configure bar auto-hide in `[modules.bar]`

If you use bar auto-hide, set it in `[modules.bar]`:

```toml
[modules.bar]
auto_hide = true          # hide bar after timeout
auto_hide_timeout = 3000  # milliseconds
```

### 5. Update widget groups syntax

`widget_groups` and `collapsible_groups` are separate sections.
Keep both if you need both behaviors.

```toml
# Widget group (inline group)
[[widget_groups]]
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]

# Collapsible group (toggleable group)
[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
tooltip = "Utility Tools"
style_classes = ["utility-tools"]
```

### 6. Add widget sections you plan to use

Older configs may be missing sections for newer widgets.
Add the ones you actually use, for example:

```toml
[widgets.settings]
icon = "󰒓"
tooltip = true
label_format = "{icon} Settings"

[widgets.wallpaper]
icon = "󰸉"
label_format = "{icon} wallpaper"
tooltip = true

[widgets.overview_button]
icon = "󰡃"
label_format = "{icon} overview"
tooltip = true
```

### 7. Update Matugen theming (if used)

Matugen config now lives in `config.toml` under `[matugen]`.
Start from the latest theme example:

```sh
cp ~/.config/tsumiki/example/config.toml ~/.config/tsumiki/config.toml
```

Then re-apply your custom colors.

### 8. Update Hyprland layer rules

Ensure your `hyprland.conf` targets `tsumiki`:

```sh
layerrule = blur, ^tsumiki$
layerrule = xray 0, ^tsumiki$
layerrule = blurpopups, ^tsumiki$
layerrule = ignorezero, ^tsumiki$
```

</Steps>

---

## Removed features

| Feature                        | Status                                            |
| ------------------------------ | ------------------------------------------------- |
| Cheatsheet module              | Configure in `[modules.cheatsheet]`               |
| `always_occluded` dock option  | Removed — use `[modules.dock]` behavior options   |
| `all_visible` widget parameter | Removed — visibility is now derived automatically |
| `CircleImage` class (internal) | Renamed to `CircularImage`                        |

---

## New features in v3

These are optional but recommended:

- **Settings GUI** — in-app settings editor (`[widgets.settings]`)
- **Multi-monitor support** — configure per-monitor bars
- **Swipe-to-dismiss** notifications
- **Notification battery alerts** — configure under `[widgets.battery.notifications]`
- **Custom widget entries** — add script-backed widgets via `[widgets."custom/<name>"]`
- **Matugen palette theming** — auto-generate colours from your wallpaper

---

## Getting help

If you run into issues after migrating:

- Check the [FAQ](/en/help/faq)
- Open an issue on [GitHub](https://github.com/rubiin/tsumiki/issues)
- Join the [Discord](https://discord.gg/8nWbDC4SnP)

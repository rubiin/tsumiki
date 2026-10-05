---
title: 配置
description: Tsumiki 配置选项和组件设置
---

Tsumiki 使用 TOML 进行配置。

## 快速入门示例

```toml
"$schema" = "./tsumiki.schema.json"

[general]
debug = false
auto_restart = true

[layout]
left_section = ["workspaces", "window_title"]
middle_section = ["date_time"]
right_section = ["volume", "battery", "system_tray"]

[modules.bar]
layer = "top"
location = "top"

[widgets.workspaces]
count = 10
hide_unoccupied = true

[widgets.volume]
tooltip = true
step_size = 5

[widgets.battery]
label = true
tooltip = true
```

## 主要部分

### `general`

全局行为，如调试模式、自动重启。

### `layout`

控制组件在状态栏中的位置。

### `modules`

启用和配置更大的 UI 模块。

### `widgets`

每个组件的设置（图标、标签、间隔）。

## 组件组

```toml
[[widget_groups]]
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]

[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
label_format = "{icon}"
tooltip = "工具"
```

## Matugen 主题生成

```toml
[matugen]
enabled = true
wallpaper = "~/Pictures/wallpaper.jpg"
scheme = "scheme-tonal-spot"
mode = "dark"
```

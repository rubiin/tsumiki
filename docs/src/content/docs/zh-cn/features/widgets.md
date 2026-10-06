---
title: 组件参考
description: 所有 Tsumiki 组件的完整配置参考
sidebar:
  order: 1
---

## 系统

```toml
[widgets.cpu]
mode = "graph"

[widgets.memory]
mode = "label"

[widgets.gpu]
mode = "circular"

[widgets.storage]
path = "/"

[widgets.network_usage]
label_format = "{upload}  {download} "

[widgets.updates]
os = "arch"
```

## 硬件

```toml
[widgets.battery]
label_format = "{percent}"

[widgets.volume]
step_size = 5

[widgets.brightness]
step_size = 5

[widgets.power]
confirm = true
```

## 桌面

```toml
[widgets.workspaces]
count = 10
style = "numbered"
show_special = false
show_urgent = false

[widgets.window_title]
truncation = true

[widgets.taskbar]
icon_size = 22
show_current_workspace_only = false
```

## 媒体

```toml
[widgets.mpris]
label_format = "{title} - {artist}"

[widgets.cava]
bars = 10
color = "#89b4fa"
```

## 集成

```toml
[widgets.github_tray]
username = "rubiin"
max_repos = 10
```

## 组

```toml
[[widget_groups]]
widgets = ["workspaces", "window_title"]
spacing = 2
style_classes = ["compact"]

[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
label_format = "󰍽"
```

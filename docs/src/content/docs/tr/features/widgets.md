---
title: Widget'lar Referansı
description: Tüm Tsumiki widget'ları için tam yapılandırma referansı
sidebar:
  order: 1
---

## Sistem

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

## Donanım

```toml
[widgets.battery]
label_format = "{icon} {percent}"

[widgets.volume]
step_size = 5

[widgets.brightness]
step_size = 5

[widgets.power]
confirm = true
```

## Masaüstü

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

## Medya

```toml
[widgets.mpris]
label_format = "{title} - {artist}"

[widgets.cava]
bars = 10
color = "#89b4fa"
```

## Entegrasyon

```toml
[widgets.github_tray]
username = "rubiin"
max_repos = 10
```

## Gruplar

```toml
[[widget_groups]]
widgets = ["workspaces", "window_title"]
spacing = 2
style_classes = ["compact"]

[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
label_format = "{icon}"
```

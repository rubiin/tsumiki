---
title: Widgets-Referenz
description: Vollständige Konfigurationsreferenz für alle Tsumiki-Widgets
sidebar:
  order: 1
---

Widgets werden unter `[widgets.<name>]` in `config.toml` konfiguriert und über `layout`-Abschnitte in der Leiste platziert.

## Systeminformations-Widgets

```toml
[widgets.cpu]
mode = "graph"
graph_length = 4

[widgets.memory]
mode = "label"
unit = "gb"

[widgets.gpu]
mode = "circular"

[widgets.storage]
path = "/"
mode = "label"

[widgets.network_usage]
label_format = "{upload}   {download} "

[widgets.updates]
os = "arch"
interval = 3600
```

## Hardware- und Energiewidgets

```toml
[widgets.battery]
label_format = "{percent}"

[widgets.volume]
step_size = 5

[widgets.brightness]
step_size = 5

[widgets.power]
label_format = ""
confirm = true
```

## Desktop- und Arbeitsbereichswidgets

```toml
[widgets.workspaces]
count = 10
style = "numbered"
show_special = false
show_urgent = false

[widgets.window_title]
truncation = true
fallback_icon = "󰣆"

[widgets.taskbar]
icon_size = 22
show_current_workspace_only = false
```

## Datums-, Zeit- und Kalenderwidgets

```toml
[widgets.date_time]
clock_format = "12h"

[widgets.world_clock]
timezones = ["America/New_York", "Asia/Tokyo"]
```

## Medien- und Audiowidgets

```toml
[widgets.mpris]
label_format = "{title} - {artist}"

[widgets.cava]
bars = 10
color = "#89b4fa"
```

## System-Dienstprogramme

```toml
[widgets.screenshot]
label_format = ""
annotation = true

[widgets.recorder]
audio = true

[widgets.clipboard]
label_format = ""
show_images = true

[widgets.usb_manager]
label_format = ""
auto_refresh = true
```

## UI- und Anwendungswidgets

```toml
[widgets.system_tray]
icon_size = 16

[widgets.github_tray]
username = "rubiin"
max_repos = 10

[widgets.weather]
location = "kathmandu"
provider = "open-meteo"
```

## Widget-Gruppen

```toml
[[widget_groups]]
widgets = ["workspaces", "window_title"]
spacing = 2
style_classes = ["compact"]

[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
label_format = "󰍽"
tooltip = "Werkzeuge"
```

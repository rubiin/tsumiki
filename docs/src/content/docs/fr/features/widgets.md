---
title: Référence des Widgets
description: Référence complète de configuration pour tous les widgets Tsumiki
sidebar:
  order: 1
---

Cette page documente chaque widget disponible dans Tsumiki, ses options de configuration, ses valeurs par défaut et son comportement.

Les widgets sont configurés sous `[widgets.<nom>]` dans `config.toml` et placés dans la barre via les sections `layout`.

---

## Widgets d'Informations Système

```toml
[widgets.cpu]
mode = "graph"          # "label" | "graph" | "circular"
graph_length = 4

[widgets.memory]
mode = "label"
graph_length = 4
unit = "gb"

[widgets.gpu]
mode = "circular"

[widgets.storage]
path = "/"
mode = "label"
unit = "gb"

[widgets.network_usage]
label_format = "{upload}   {download} "
interval = 2000

[widgets.updates]
os = "arch"
interval = 3600
flatpak = true
```

## Widgets Matériel et Alimentation

```toml
[widgets.battery]
label_format = "{icon} {percent}"

[widgets.volume]
step_size = 5

[widgets.brightness]
step_size = 5

[widgets.bluetooth]
label_format = "{icon} Bluetooth"

[widgets.microphone]
label_format = "{icon} Mic"

[widgets.power]
icon = "󰐥"
confirm = true

[widgets.hypridle]
enabled_icon = ""
label_format = "{icon}"
disabled_icon = ""

[widgets.hyprsunset]
label_format = "{icon}"
temperature = "2800k"
```

## Widgets de Bureau et Espaces de Travail

```toml
[widgets.workspaces]
count = 10
style = "numbered"
show_special = false
show_urgent = false

[widgets.window_title]
truncation = true
truncation_size = 50

[widgets.window_count]
hide_when_zero = true

[widgets.taskbar]
icon_size = 22
show_current_workspace_only = false
```

## Widgets de Date, Heure et Calendrier

```toml
[widgets.date_time]
clock_format = "12h"
calendar = true

[widgets.world_clock]
timezones = ["America/New_York", "Asia/Tokyo"]
```

## Widgets Média et Audio

```toml
[widgets.mpris]
label_format = "{title} - {artist}"
hide_when_no_player = true

[widgets.cava]
bars = 10
color = "#89b4fa"
```

## Utilitaires Système

```toml
[widgets.screenshot]
label_format = "{icon}"
annotation = true

[widgets.recorder]
audio = true

[widgets.ocr]
quiet = false

[widgets.clipboard]
label_format = "{icon}"
show_images = true
enable_pinning = true

[widgets.usb_manager]
label_format = "{icon}"
auto_refresh = true
```

## Widgets d'Interface et d'Applications

```toml
[widgets.quick_settings]
hover_reveal = false

[widgets.system_tray]
icon_size = 16

[widgets.wallpaper]
icon = "󰸉"
label_format = "{icon} wallpaper"

[widgets.settings]
icon = "󰒓"

[widgets.theme_switcher]
icon = ""

[widgets.emoji_picker]
label_format = "{icon} Emoji"
per_row = 9

[widgets.kanban]
icon = "󱞁"
label_format = "{icon} Kanban"

[widgets.pomodoro]
icon = "🍅"

[widgets.github_tray]
username = "rubiin"
max_repos = 10

[widgets.cloudflare_warp]
label_format = "{icon}"

[widgets.dns_switcher]
icon = "󰚘"

[widgets.weather]
location = "kathmandu"
provider = "open-meteo"

[widgets.ip_monitor]
icon = "󰖟"
label_format = "{icon}"
```

## Widgets de Disposition et de Groupement

### Bouton Personnalisé

Voir la [Configuration Avancée](/fr/configuring/advanced) pour la configuration et l'utilisation.

### Groupe de Boutons Personnalisés

Voir la [Configuration Avancée](/fr/configuring/advanced) pour la configuration et l'utilisation.

### Widget Personnalisé

Voir la [Configuration Avancée](/fr/configuring/advanced) pour la configuration et l'utilisation.

## Groupes de Widgets et Groupes Pliables

```toml
[[widget_groups]]
widgets = ["workspaces", "window_title"]
spacing = 2
style_classes = ["compact"]

[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
tooltip = "Outils utilitaires"
style_classes = ["utility-tools"]
```

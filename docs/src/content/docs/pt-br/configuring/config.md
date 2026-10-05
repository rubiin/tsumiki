---
title: Configuração
description: Opções de configuração do Tsumiki e ajustes de widgets
---

Tsumiki usa TOML para configuração.

## Exemplo de Início Rápido

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

## Seções Principais

### `general`

Comportamento global como modo de depuração, reinicialização automática.

### `layout`

Controla o posicionamento de widgets nas seções da barra.

### `modules`

Ativa e configura módulos de UI maiores.

### `widgets`

Configuração por widget (ícones, rótulos, intervalos).

## Grupos de Widgets

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
tooltip = "Ferramentas"
```

## Geração de Temas Matugen

```toml
[matugen]
enabled = true
wallpaper = "~/Pictures/wallpaper.jpg"
scheme = "scheme-tonal-spot"
mode = "dark"
```

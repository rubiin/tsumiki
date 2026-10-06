---
title: Configuratie
description: Tsumiki-configuratieopties en widgetinstellingen
---

Tsumiki gebruikt TOML voor configuratie.

## Configuratiebestanden

- `config.toml`: widgets, lay-out, modules, runtime-gedrag.
- `tsumiki.schema.json`: schemabron van waarheid.

:::note
Het schema vereist `widget_groups` en `collapsible_groups` secties op het hoogste niveau.
Beginnen met `example/config.toml` is de veiligste manier om schema-geldig te blijven.
:::

## Snelstart Voorbeeld

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
label_format = "󰍽"
tooltip = "Hulpmiddelen"
style_classes = ["utility-tools"]

[modules.bar]
layer = "top"
location = "top"
auto_hide = false
auto_hide_timeout = 3000

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

## Hoofdsecties

### `general`

Wereldwijd gedrag zoals debug-modus, automatisch herstarten en multi-monitor bediening.

### `layout`

Bepaalt de widgetplaatsing in balk secties via `left_section`, `middle_section`, `right_section`.

### `modules`

Schakelt grotere UI-modules in en configureert ze, zoals de balk, dock, meldingen, OSD, en meer.

### `widgets`

Instellingen per widget (pictogrammen, labels, drempels, polling-intervallen, gedragsvlaggen).

## Widget Groepen & Inklapbare Groepen

```toml
[[widget_groups]]
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]

[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
label_format = "󰍽"
tooltip = "Hulpmiddelen"
style_classes = ["utility-tools"]
```

## Matugen Thema Generatie

```toml
[matugen]
enabled = true
wallpaper = "~/Pictures/wallpaper.jpg"
scheme = "scheme-tonal-spot"
mode = "dark"
```

---
title: Yapılandırma
description: Tsumiki yapılandırma seçenekleri ve widget ayarları
---

Tsumiki, yapılandırma için TOML kullanır.

## Hızlı Başlangıç Örneği

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

## Ana Bölümler

### `general`

Hata ayıklama modu, otomatik yeniden başlatma gibi genel davranış.

### `layout`

Widget'ların çubuktaki yerleşimini kontrol eder.

### `modules`

Daha büyük UI modüllerini etkinleştirir ve yapılandırır.

### `widgets`

Widget başına ayarlar (simgeler, etiketler, aralıklar).

## Widget Grupları

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
tooltip = "Araçlar"
```

## Matugen Tema Oluşturma

```toml
[matugen]
enabled = true
wallpaper = "~/Pictures/wallpaper.jpg"
scheme = "scheme-tonal-spot"
mode = "dark"
```

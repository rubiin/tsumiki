---
title: Erweiterte Konfiguration
description: Erweiterte Tsumiki-Konfigurationsmuster
---

Sobald Sie mit den [Konfigurations](/de/configuring/config)-Grundlagen vertraut sind, helfen Ihnen diese Muster, Tsumiki weiter anzupassen.

## Benutzerdefiniertes Widget

Waybar-kompatible benutzerdefinierte Widgets, die externe Shell-Befehle mit konfigurierbarer Ausgabeanalyse und Klickbehandlung ausführen.

```toml
[[widgets.custom_widget]]
id = "volume"
exec = "pamixer --get-volume"
label_format = "󰕾 {}%"
interval = 1000
on_scroll_up = "pamixer -i 5"
on_scroll_down = "pamixer -d 5"
exec_on_event = true

[layout]
left_section = ["@custom_widget:volume", "workspaces"]
```

Vollständige Konfigurationsoptionen:

| Schlüssel          | Typ    | Standard  | Beschreibung                                                          |
| ------------------ | ------ | --------- | --------------------------------------------------------------------- |
| `id`               | string | —         | Eindeutige Kennung für Referenz im Layout (`@custom_widget:meine-id`) |
| `exec`             | string | —         | Auszuführender Shell-Befehl; weglassen für einen reinen Klick-Button  |
| `icon`             | string | —         | Statisches Icon, entspricht `format_icons.default`                    |
| `interval`         | int    | `0`       | Aktualisierungsintervall in Millisekunden (0 = einmal ausführen)      |
| `return_type`      | string | `"plain"` | Ausgabeformat: `"plain"` oder `"json"`                                |
| `label_format`     | string | `"{}"`    | Formatzeichenfolge, bei der `{}` durch die Ausgabe ersetzt wird       |
| `format`           | string | —         | Waybars Name für `label_format`                                       |
| `exec_on_event`    | bool   | `false`   | Befehl nach Klick/Scrollen erneut ausführen                           |
| `max_length`       | int    | `0`       | Maximale Textlänge (0 = kein Limit)                                   |
| `min_length`       | int    | `0`       | Minimale Textlänge (füllt mit Leerzeichen)                            |
| `rotate`           | int    | `0`       | Text um Grad drehen                                                   |
| `tooltip`          | bool   | `true`    | Tooltip mit Ausgabe anzeigen                                          |
| `tooltip_format`   | string | —         | Tooltip-Formatzeichenfolge                                            |
| `tooltip_text`     | string | —         | Statischer Tooltip, wenn sich die Ausgabe nie ändert                  |
| `on_click`         | string | —         | Linksklick-Befehl                                                     |
| `on_click_right`   | string | —         | Rechtsklick-Befehl                                                    |
| `on_click_middle`  | string | —         | Mittelklick-Befehl                                                    |
| `on_scroll_up`     | string | —         | Scrollen-nach-oben-Befehl                                             |
| `on_scroll_down`   | string | —         | Scrollen-nach-unten-Befehl                                            |
| `signal`           | int    | —         | Signalnummer für sig* Ereignisauslöser                                |
| `restart_interval` | int    | —         | Neustartintervall für persistente Skripte                             |

## Widget-Gruppen

Gruppieren Sie Widgets mit gemeinsamem Abstand und Stil:
Referenzieren Sie eine Gruppe in Ihrem Layout mit `@group:N` (nullbasierter Index) oder `@group:id` (Textkennung):

```toml
[[widget_groups]]
id = "sys-group"
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

Referenzieren Sie im Layout mit `@group:sys-group`.

```toml
[layout]
right_section = ["@group:sys-group", "system_tray"]
```

## Einklappbare Gruppen

Verbergen Sie weniger verwendete Widgets hinter einem Umschalter:

```toml
[[collapsible_groups]]
id = "utility-tools"
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
label_format = "{icon}"
tooltip = "Werkzeuge"
style_classes = ["utility-tools"]
```

Referenzieren Sie im Layout mit `@collapsible:utility-tools`.

```toml

right_section = ["@collapsible:utility-tools", "system_tray"]

```

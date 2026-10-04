---
title: Konfiguration
description: Tsumiki-Konfigurationsoptionen und Widget-Einstellungen
---

Tsumiki verwendet TOML für die Konfiguration.

## Konfigurationsdateien

- `config.toml`: Widgets, Layout, Module, Laufzeitverhalten.
- `tsumiki.schema.json`: Schema-Quelle der Wahrheit.

:::note
Das Schema erfordert `widget_groups`- und `collapsible_groups`-Abschnitte auf oberster Ebene.
Der sicherste Weg, schema-konform zu bleiben, ist mit `example/config.toml` zu beginnen.
:::

## Schnellstart-Beispiel

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
icon = "󰒓"
tooltip = "Werkzeuge"
style_classes = ["utility-tools"]

[modules.bar]
layer = "top"
location = "top"
auto_hide = false
auto_hide_timeout = 3000

[widgets.workspaces]
count = 10
hide_unoccupied = true

[widgets.date_time]
date_format = "%b %d %H:%M"

[widgets.volume]
tooltip = true
step_size = 5

[widgets.battery]
label = true
tooltip = true
```

## Hauptabschnitte

### `general`

Globales Verhalten wie Debug-Modus, automatischer Neustart und Multi-Monitor-Steuerung.

| Schlüssel        | Typ  | Standard | Beschreibung                             |
| ---------------- | ---- | -------- | ---------------------------------------- |
| `debug`          | bool | `false`  | Ausführliche Protokollierung aktivieren  |
| `auto_restart`   | bool | `true`   | Automatischer Neustart bei Absturz       |
| `restart_delay`  | int  | `1500`   | Verzögerung vor Neustart (ms)            |
| `multi_monitor`  | bool | `false`  | Pro-Monitor-Leisteninstanzen             |
| `tooltips`       | bool | `true`   | Widget-Tooltips aktivieren               |
| `check_updates`  | bool | `false`  | Auf Tsumiki-Updates prüfen               |
| `monitor_styles` | bool | `true`   | SCSS-Änderungen überwachen und neu laden |

### `layout`

Steuert die Widget-Platzierung in den Leistenabschnitten:

- `left_section`
- `middle_section`
- `right_section`

Jeder Wert ist eine Liste von Widget-IDs. Verwenden Sie `@group:N` (nullbasierter Index) für Widget-Gruppen:

```toml
[layout]
left_section = ["@group:0", "window_title"]
middle_section = ["date_time"]
right_section = ["@group:1", "system_tray", "power"]
```

Verfügbare Referenztypen:

| Referenz           | Beispiel             | Beschreibung                          |
| ------------------ | -------------------- | ------------------------------------- |
| Widget-Name        | `"workspaces"`       | Direkte Widget-Referenz               |
| `@group:N`         | `"@group:0"`         | Widget-Gruppe nach Index              |
| `@collapsible:N`   | `"@collapsible:0"`   | Einklappbare Gruppe nach Index        |
| `@custom_button:N` | `"@custom_button:0"` | Benutzerdefinierter Button nach Index |

### `modules`

Aktiviert und konfiguriert größere UI-Module wie:

| Modul              | Schlüssel                | Beschreibung                          |
| ------------------ | ------------------------ | ------------------------------------- |
| Leiste             | `modules.bar`            | Panel-Position und -Ebene             |
| Benachrichtigungen | `modules.notification`   | Desktop-Benachrichtigungssystem       |
| Dock               | `modules.dock`           | App-Dock mit Intellihide              |
| Übersicht          | `modules.overview`       | Arbeitsbereichs-Exposé-Ansicht        |
| OSD                | `modules.osd`            | Bildschirmanzeige für Lautstärke usw. |
| Launcher           | `modules.launcher`       | Anwendungssuche und -start            |
| Desktop-Uhr        | `modules.desktop_clock`  | Dekorative Desktop-Uhr                |
| Desktop-Zitate     | `modules.desktop_quotes` | Inspirierende Zitate-Überlagerung     |
| Bildschirmecken    | `modules.screen_corners` | Aktive Ecken                          |
| Spickzettel        | `modules.cheatsheet`     | Tastenkürzel-Referenz                 |
| Activate Linux     | `modules.activate_linux` | Fensteraktivierungs-Hinweis           |

Beispiel für eine Dock-Konfiguration:

```toml
[modules.dock]
enabled = true
behavior = "intellihide"
show_when_no_windows = false
icon_size = 40
```

Siehe die [Module-Referenz](/de/features/modules) für vollständige Optionen.

### `widgets`

Pro-Widget-Einstellungen (Symbole, Beschriftungen, Schwellenwerte, Abfrageintervalle, Verhaltensflags).

Es stehen über 45 Widgets zur Verfügung. Siehe die vollständige [Widgets-Referenz](/de/features/widgets) für jede Option.

Häufige Widgets sind:

| Widget           | Beschreibung                      |
| ---------------- | --------------------------------- |
| `workspaces`     | Virtueller Desktop-Umschalter     |
| `window_title`   | Aktiver Fenstertitel              |
| `date_time`      | Datums-/Zeitanzeige               |
| `system_tray`    | System Tray-Symbole               |
| `volume`         | Audio-Lautstärkeregelung          |
| `battery`        | Akkustatus                        |
| `cpu`            | CPU-Auslastungsmonitor            |
| `memory`         | Speicherauslastungsmonitor        |
| `network_usage`  | Netzwerkgeschwindigkeitsmonitor   |
| `weather`        | Wetterbedingungen                 |
| `power`          | Energiemenü (Herunterfahren usw.) |
| `quick_settings` | Schnelleinstellungen-Panel        |

## Arbeitsbereichs-Stile

Das Arbeitsbereichs-Widget unterstützt sechs Anzeigestile:

```toml
[widgets.workspaces]
style = "numbered"   # "numbered" | "pill" | "icon" | "minimal" | "underline" | "bubble"
```

- **numbered** — Zahlen mit pillenförmigem Aktiv-Indikator (Standard)
- **pill** — Minimale Pillen-Indikatoren ohne Text
- **icon** — Benutzerdefinierte Nerd Font-Symbole pro Arbeitsbereich
- **minimal** — Sauber, dezent mit subtilem Hintergrund
- **underline** — Aktiver Arbeitsbereich erhält unteren Randakzent, kein Hintergrund
- **bubble** — Kreisförmige Blasenbehälter

## Widget-Gruppen und einklappbare Gruppen

Gruppieren Sie Widgets mit gemeinsamem Abstand und Stil:

```toml
[[widget_groups]]
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

Einklappbare Gruppen verbergen Widgets hinter einem Umschalter:

```toml
[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
tooltip = "Werkzeuge"
style_classes = ["utility-tools"]
```

Referenzieren Sie Gruppen im Layout mit `@group:N` oder `@collapsible:N`.

## Matugen-Theme-Generierung

Generieren Sie automatisch Farbpaletten aus Ihrem Hintergrundbild:

```toml
[matugen]
enabled = true
wallpaper = "~/Pictures/wallpaper.jpg"
scheme = "scheme-tonal-spot"
mode = "dark"
contrast = 0.0
```

Siehe [Theming mit Matugen](/de/theming/matugen) für Details.

## Migrationshinweis

Wenn Sie von älteren Versionen aktualisieren, lesen Sie [Migration v2 zu v3](/de/resources/migration-v2-v3), bevor Sie alte Konfigurationsblöcke kopieren.

## Empfohlener Arbeitsablauf

1. Beginnen Sie mit `example/config.toml`.
2. Halten Sie Ihre benutzerdefinierte Datei klein und fokussiert.
3. Ändern Sie jeweils einen Abschnitt.
4. Starten Sie mit `./tsumiki.sh -start` neu, um das Verhalten zu validieren.

## Referenzquelle

Diese Seite ist ein praktischer Überblick.
Vollständige Schlüsseldefinitionen und Standardwerte finden Sie in der [Widgets-Referenz](/de/features/widgets) und der [Module-Referenz](/de/features/modules).
Das vollständige Schema finden Sie in `tsumiki.schema.json` im Projektstammverzeichnis.

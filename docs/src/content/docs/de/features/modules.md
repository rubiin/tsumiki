---
title: Module-Referenz
description: Vollständige Dokumentation aller Tsumiki-Module
sidebar:
  order: 2
---

Module sind größere UI-Oberflächen, die über die Leiste hinausgehen, wie Dock, Benachrichtigungen, Übersicht und OSD.

## Leiste

```toml
[modules.bar]
layer = "top"
auto_hide = false
auto_hide_timeout = 3000
location = "top"
```

## Benachrichtigungssystem

```toml
[modules.notification]
enabled = true
anchor = "top-right"
auto_dismiss = true
transition_type = "slide-left"
```

## Dock

```toml
[modules.dock]
enabled = false
icon_size = 40
behavior = "intellihide"
group_apps = true
```

## Übersicht

```toml
[modules.overview]
enabled = false
layer = "top"
anchor = "center"
transition_type = "crossfade"
```

## Launcher

```toml
[modules.launcher]
enabled = false
tooltip = true
icon_size = 35
anchor = "center"
width = 280
height = 320
layout = "grid"
grid_columns = 3
grid_spacing = 12
plugins_enabled = true
plugins_dir = ""
```

Tippe `/` ein, um Slash-Befehle wie `/calc` oder `/translate` zu verwenden. Plugins sind Python-Dateien im `plugins/`-Verzeichnis.

Gebündelte Plugins:

- **`/calc`** — Mathematik, Einheiten und Währungen über libqalculate (`qalc`), z. B. `/calc 100 cm to inches`.
- **`/translate`** — Übersetzung mit automatisch erkannter Ausgangssprache, z. B. `/translate bonjour`.
- **`/emoji`** — Offline-Emoji-Suche, z. B. `/emoji rocket`.
- **`/clipboard-history`** — durchsucht den `cliphist`-Verlauf und kopiert einen Eintrag zurück, z. B. `/clipboard-history https://`.
- **`/currency`** — Währungsumrechnung mit Live-Kursen (Frankfurter, kein API-Schlüssel), z. B. `/currency 100 usd to eur`.
- **`/kill`** — sucht laufende Prozesse und beendet den ausgewählten (SIGTERM oder SIGKILL mit `-9`), z. B. `/kill firefox`. Ein numerisches Argument wird als Port behandelt — `/kill 3000` beendet, was auf Port 3000 lauscht.
- **`/search`** — Websuche (DuckDuckGo, kein API-Schlüssel) und öffnet ein Ergebnis im Browser, während die URL in die Zwischenablage kopiert wird, z. B. `/search fabric hyprland`.

Tastatur: `Auf`/`Ab` bewegen die Auswahl, `Enter` aktiviert die markierte Zeile, `Escape` schließt.

## OSD

```toml
[modules.osd]
enabled = false
timeout = 3000
osds = ["brightness", "volume"]
```

## Desktop-Uhr

```toml
[modules.desktop_clock]
enabled = false
type = "cookie"
layer = "bottom"
nepali_date = false
```

## Desktop-Zitate

```toml
[modules.desktop_quotes]
enabled = false
interval = 600
```

## Activate Linux

```toml
[modules.activate_linux]
enabled = false
```

## Bildschirmecken

```toml
[modules.screen_corners]
enabled = false
size = 20
```

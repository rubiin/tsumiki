---
title: Modules Referentie
description: Volledige documentatie van alle Tsumiki-modules
sidebar:
  order: 2
---

Modules zijn grotere UI-oppervlakken die verder gaan dan de balk, zoals het dock, meldingen, overzicht en OSD.

## Balk

```toml
[modules.bar]
layer = "top"
auto_hide = false
auto_hide_timeout = 3000
location = "top"
```

## Meldingensysteem

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
orientation = "horizontal"
```

## Overzicht

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

Typ `/` om slash-commando's zoals `/calc` of `/translate` te gebruiken. Plugins zijn Python-bestanden in de map `plugins/`.

Ingebouwde plugins:

- **`/calc`** — rekenen, eenheden en valuta via libqalculate (`qalc`), bv. `/calc 100 cm to inches`.
- **`/translate`** — vertaling met automatisch gedetecteerde brontaal, bv. `/translate bonjour`.
- **`/emoji`** — offline emoji-zoekopdracht, bv. `/emoji rocket`.
- **`/clipboard-history`** — doorzoek de `cliphist`-geschiedenis en kopieer een item terug, bv. `/clipboard-history https://`.
- **`/currency`** — valuta omrekenen met live wisselkoersen (Frankfurter, geen API-sleutel), bv. `/currency 100 usd to eur`.
- **`/kill`** — zoek actieve processen en beëindig het geselecteerde (SIGTERM, of SIGKILL met `-9`), bv. `/kill firefox`. Een numeriek argument wordt als poort behandeld — `/kill 3000` beëindigt wat er op poort 3000 luistert.
- **`/search`** — zoek op het web (DuckDuckGo, geen API-sleutel) en open een resultaat in je browser terwijl de URL naar het klembord wordt gekopieerd, bv. `/search fabric hyprland`.

Toetsenbord: `Omhoog`/`Omlaag` verplaatst de selectie, `Enter` activeert de gemarkeerde rij, `Escape` sluit.

## OSD

```toml
[modules.osd]
enabled = false
timeout = 3000
osds = ["brightness", "volume"]
```

## Desktopklok

```toml
[modules.desktop_clock]
enabled = false
type = "cookie"
layer = "bottom"
nepali_date = false
```

## Desktopcitaten

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

## Schermhoeken

```toml
[modules.screen_corners]
enabled = false
size = 20
```

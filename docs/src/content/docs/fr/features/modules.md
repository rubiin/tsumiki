---
title: Référence des Modules
description: Documentation complète de tous les modules Tsumiki
sidebar:
  order: 2
---

Les modules sont des surfaces d'interface plus grandes qui vont au-delà de la barre, comme le dock, les notifications, la vue d'ensemble et l'OSD. Ils sont configurés sous `[modules.<nom>]` dans `config.toml`.

Contrairement aux widgets, la plupart des modules sont des fenêtres autonomes ou des superpositions qui doivent être explicitement activés.

---

## Barre

La barre elle-même est un module.

```toml
[modules.bar]
layer = "top"
auto_hide = false
auto_hide_timeout = 3000
location = "top"
```

## Système de Notifications

Affiche les notifications du bureau.

```toml
[modules.notification]
enabled = true
anchor = "top-right"
auto_dismiss = true
dnd_on_screencast = true
transition_type = "slide-left"
transition_duration = 350
```

## Dock

Lanceur d'applications épinglées avec intellihide.

```toml
[modules.dock]
enabled = false
icon_size = 40
behavior = "intellihide"
group_apps = true
orientation = "horizontal"
```

## Aperçu (Exposé des espaces de travail)

Vue plein écran de tous les espaces de travail.

```toml
[modules.overview]
enabled = false
layer = "top"
anchor = "center"
transition_type = "crossfade"
transition_duration = 350
```

## Lanceur d'Applications

Lanceur d'applications piloté par clavier.

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

Tapez `/` pour utiliser des commandes slash comme `/calc` ou `/translate`. Les plugins sont des fichiers Python placés dans `plugins/`.

Plugins inclus :

- **`/calc`** — mathématiques, unités et devises via libqalculate (`qalc`), p. ex. `/calc 100 cm to inches`.
- **`/translate`** — traduction avec détection automatique de la langue source, p. ex. `/translate bonjour`.
- **`/emoji`** — recherche d'emojis hors ligne, p. ex. `/emoji rocket`.
- **`/clipboard-history`** — recherche dans l'historique `cliphist` et recopie un élément, p. ex. `/clipboard-history https://`.
- **`/currency`** — conversion de devises avec taux en direct (Frankfurter, sans clé API), p. ex. `/currency 100 usd to eur`.
- **`/kill`** — recherche les processus en cours et tue celui sélectionné (SIGTERM, ou SIGKILL avec `-9`), p. ex. `/kill firefox`. Un argument numérique est traité comme un port — `/kill 3000` tue le processus qui écoute sur le port 3000.
- **`/search`** — recherche sur le web (DuckDuckGo, sans clé API) et ouvre un résultat dans votre navigateur tout en copiant son URL dans le presse-papiers, p. ex. `/search fabric hyprland`.

Clavier : `Haut`/`Bas` déplacent la sélection, `Entrée` active la ligne en surbrillance, `Échap` ferme.

## OSD (Affichage à l'Écran)

Superpositions transitoires pour le volume, la luminosité, etc.

```toml
[modules.osd]
enabled = false
timeout = 1500
anchor = "bottom-center"
orientation = "horizontal"
osds = ["brightness", "volume"]
```

## Horloge de Bureau

Superposition d'horloge décorative.

```toml
[modules.desktop_clock]
enabled = false
type = "cookie"
layer = "bottom"
anchor = "bottom-right"
nepali_date = false
```

## Citations de Bureau

Citations inspirantes rotatives.

```toml
[modules.desktop_quotes]
enabled = false
anchor = "bottom-right"
layer = "bottom"
interval = 600
```

## Activate Linux

Indicateur d'activation de fenêtre.

```toml
[modules.activate_linux]
enabled = false
anchor = "bottom-right"
layer = "bottom"
```

## Coins d'Écran

Coins actifs.

```toml
[modules.screen_corners]
enabled = false
size = 20
```

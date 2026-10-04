---
title: Configuration
description: Options de configuration de Tsumiki et paramètres des widgets
---

Tsumiki utilise TOML pour la configuration.

## Fichiers de Configuration

- `config.toml` : widgets, disposition, modules, comportement d'exécution.
- `tsumiki.schema.json` : schéma source de vérité.

:::note
Le schéma nécessite des sections `widget_groups` et `collapsible_groups` de niveau supérieur.
Commencer à partir de `example/config.toml` est le moyen le plus sûr de rester valide avec le schéma.
:::

## Exemple de Démarrage Rapide

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
tooltip = "Outils utilitaires"
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

## Sections Principales

### `general`

Comportement global comme le mode débogage, le redémarrage automatique et les contrôles multi-moniteurs.

| Clé              | Type | Défaut  | Description                                  |
| ---------------- | ---- | ------- | -------------------------------------------- |
| `debug`          | bool | `false` | Activer la journalisation verbose            |
| `auto_restart`   | bool | `true`  | Redémarrer automatiquement en cas de crash   |
| `restart_delay`  | int  | `1500`  | Délai avant redémarrage (ms)                 |
| `multi_monitor`  | bool | `false` | Instances de barre par moniteur              |
| `tooltips`       | bool | `true`  | Activer les infobulles des widgets           |
| `check_updates`  | bool | `false` | Vérifier les mises à jour de Tsumiki         |
| `monitor_styles` | bool | `true`  | Surveiller et recharger les changements SCSS |

### `layout`

Contrôle le placement des widgets dans les sections de la barre :

- `left_section`
- `middle_section`
- `right_section`

Chaque valeur est une liste d'IDs de widgets. Utilisez `@group:N` (index basé sur zéro) pour les groupes de widgets :

```toml
[layout]
left_section = ["@group:0", "window_title"]
middle_section = ["date_time"]
right_section = ["@group:1", "system_tray", "power"]
```

Types de référence disponibles :

| Référence          | Exemple              | Description                   |
| ------------------ | -------------------- | ----------------------------- |
| Nom du widget      | `"workspaces"`       | Référence directe au widget   |
| `@group:N`         | `"@group:0"`         | Groupe de widgets par index   |
| `@collapsible:N`   | `"@collapsible:0"`   | Groupe pliable par index      |
| `@custom_button:N` | `"@custom_button:0"` | Bouton personnalisé par index |

### `modules`

Active et configure les grands modules d'interface utilisateur tels que :

| Module                 | Clé                      | Description                              |
| ---------------------- | ------------------------ | ---------------------------------------- |
| Barre                  | `modules.bar`            | Position et couche du panneau            |
| Notifications          | `modules.notification`   | Système de notifications du bureau       |
| Dock                   | `modules.dock`           | Dock d'applications avec intellihide     |
| Aperçu                 | `modules.overview`       | Vue exposé des espaces de travail        |
| OSD                    | `modules.osd`            | Affichage à l'écran pour le volume, etc. |
| Lanceur d'applications | `modules.launcher`       | Recherche et lancement d'applications    |
| Horloge de bureau      | `modules.desktop_clock`  | Horloge décorative du bureau             |
| Citations de bureau    | `modules.desktop_quotes` | Superposition de citations inspirantes   |
| Coins d'écran          | `modules.screen_corners` | Coins actifs                             |
| Aide-mémoire           | `modules.cheatsheet`     | Référence des raccourcis clavier         |
| Activate Linux         | `modules.activate_linux` | Indicateur d'activation de fenêtre       |

Exemple de configuration du dock :

```toml
[modules.dock]
enabled = true
behavior = "intellihide"
show_when_no_windows = false
icon_size = 40
```

Voir la [Référence des Modules](/fr/features/modules) pour les options complètes.

### `widgets`

Paramètres par widget (icônes, étiquettes, seuils, intervalles de sondage, indicateurs de comportement).

Plus de 45 widgets sont disponibles. Voir la [Référence des Widgets](/fr/features/widgets) complète pour chaque option.

Les widgets courants incluent :

| Widget           | Description                            |
| ---------------- | -------------------------------------- |
| `workspaces`     | Sélecteur de bureaux virtuels          |
| `window_title`   | Titre de la fenêtre active             |
| `date_time`      | Affichage de la date/heure             |
| `system_tray`    | Icônes de la barre système             |
| `volume`         | Contrôle du volume audio               |
| `battery`        | État de la batterie                    |
| `cpu`            | Moniteur d'utilisation CPU             |
| `memory`         | Moniteur d'utilisation mémoire         |
| `network_usage`  | Moniteur de vitesse réseau             |
| `weather`        | Conditions météorologiques             |
| `power`          | Menu d'alimentation (extinction, etc.) |
| `quick_settings` | Panneau des paramètres rapides         |

## Styles d'Espaces de Travail

Le widget d'espaces de travail prend en charge six styles d'affichage :

```toml
[widgets.workspaces]
style = "numbered"   # "numbered" | "pill" | "icon" | "minimal" | "underline" | "bubble"
```

- **numbered** — Chiffres avec indicateur actif en forme de pilule (par défaut)
- **pill** — Indicateurs minimalistes sans texte
- **icon** — Icônes Nerd Font personnalisées par espace de travail
- **minimal** — Propre et discret avec fond subtil
- **underline** — L'espace de travail actif obtient une bordure inférieure, pas de fond
- **bubble** — Conteneurs à bulles circulaires

## Groupes de Widgets et Groupes Pliables

Regroupez les widgets avec un espacement et un style partagés :

```toml
[[widget_groups]]
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

Les groupes pliables cachent les widgets derrière un bouton :

```toml
[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
tooltip = "Outils utilitaires"
style_classes = ["utility-tools"]
```

Référencez les groupes dans la disposition avec `@group:N` ou `@collapsible:N`.

## Génération de Thèmes Matugen

Générez automatiquement des palettes de couleurs à partir de votre fond d'écran :

```toml
[matugen]
enabled = true
wallpaper = "~/Pictures/wallpaper.jpg"
scheme = "scheme-tonal-spot"
mode = "dark"
contrast = 0.0
```

Voir [Thématisation avec Matugen](/fr/theming/matugen) pour plus de détails.

## Note de Migration

Si vous effectuez une mise à niveau depuis des versions plus anciennes, consultez [Migration v2 vers v3](/fr/resources/migration-v2-v3) avant de copier d'anciens blocs de configuration.

## Flux de Travail Recommandé

1. Commencez à partir de `example/config.toml`.
2. Gardez votre fichier personnalisé petit et ciblé.
3. Modifiez une section à la fois.
4. Redémarrez avec `./tsumiki.sh -start` pour valider le comportement.

## Source de Référence

Cette page est un aperçu pratique.
Pour les définitions complètes des clés et les valeurs par défaut, consultez la [Référence des Widgets](/fr/features/widgets) et la [Référence des Modules](/fr/features/modules).
Pour le schéma complet, utilisez `tsumiki.schema.json` à la racine du projet.

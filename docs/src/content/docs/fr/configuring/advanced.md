---
title: Configuration Avancée
description: Modèles de configuration avancée de Tsumiki
---

Une fois que vous êtes à l'aise avec les bases de la [Configuration](/fr/configuring/config), ces modèles vous aident à affiner Tsumiki davantage.

## Widget Personnalisé

Widgets personnalisés compatibles Waybar qui exécutent des commandes shell externes avec une analyse de sortie configurable et une gestion des clics.

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

Options de configuration complètes :

| Clé                | Type   | Défaut    | Description                                                                      |
| ------------------ | ------ | --------- | -------------------------------------------------------------------------------- |
| `id`               | string | —         | Identifiant unique pour référencer dans la disposition (`@custom_widget:mon-id`) |
| `exec`             | string | —         | Commande shell à exécuter ; omettez pour un bouton uniquement au clic            |
| `icon`             | string | —         | Glyphe d'icône statique, équivalent à `format_icons.default`                     |
| `interval`         | int    | `0`       | Intervalle d'actualisation en millisecondes (0 = exécuter une fois)              |
| `return_type`      | string | `"plain"` | Format de sortie : `"plain"` ou `"json"`                                         |
| `label_format`     | string | `"{}"`    | Chaîne de format où `{}` est remplacé par la sortie                              |
| `format`           | string | —         | Le nom de `label_format` chez Waybar                                             |
| `exec_on_event`    | bool   | `false`   | Ré-exécuter la commande après clic/défilement                                    |
| `max_length`       | int    | `0`       | Longueur maximale du texte (0 = pas de limite)                                   |
| `min_length`       | int    | `0`       | Longueur minimale du texte (remplit avec des espaces)                            |
| `rotate`           | int    | `0`       | Rotation du texte en degrés                                                      |
| `tooltip`          | bool   | `true`    | Afficher l'infobulle avec la sortie                                              |
| `tooltip_format`   | string | —         | Chaîne de format de l'infobulle                                                  |
| `tooltip_text`     | string | —         | Infobulle statique, pour un widget dont la sortie ne change jamais               |
| `on_click`         | string | —         | Commande clic gauche                                                             |
| `on_click_right`   | string | —         | Commande clic droit                                                              |
| `on_click_middle`  | string | —         | Commande clic milieu                                                             |
| `on_scroll_up`     | string | —         | Commande défilement vers le haut                                                 |
| `on_scroll_down`   | string | —         | Commande défilement vers le bas                                                  |
| `signal`           | int    | —         | Numéro de signal pour les déclencheurs d'événements sig*                         |
| `restart_interval` | int    | —         | Intervalle de redémarrage pour les scripts persistants                           |

## Groupes de Widgets

Regroupez les widgets avec un espacement et un style partagés :
Référencez un groupe dans votre disposition avec `@group:N` (index basé sur zéro) ou `@group:id` (identifiant textuel) :

```toml
[[widget_groups]]
id = "sys-group"
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

Référencez dans la disposition avec `@group:sys-group`.

```toml
[layout]
right_section = ["@group:sys-group", "system_tray"]
```

## Groupes Pliables

Cachez les widgets moins utilisés derrière un bouton :

```toml
[[collapsible_groups]]
id = "utility-tools"
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
label_format = "{icon}"
tooltip = "Outils utilitaires"
style_classes = ["utility-tools"]
```

Référencez dans la disposition avec `@collapsible:utility-tools`.

```toml

right_section = ["@collapsible:utility-tools", "system_tray"]

```

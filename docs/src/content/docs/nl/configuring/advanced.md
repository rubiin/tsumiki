---
title: Geavanceerde Configuratie
description: Geavanceerde Tsumiki-configuratiepatronen
---

Zodra u vertrouwd bent met de [Configuratie](/nl/configuring/config) basisprincipes, helpen deze patronen u om Tsumiki verder af te stemmen.

## Aangepaste Widget

Waybar-compatibele aangepaste widgets die externe shell-commando's uitvoeren met configureerbare uitvoerparsing en klikafhandeling.

```toml
[[widgets.custom_widget]]
id = "volume"
exec = "pamixer --get-volume"
format = "󰕾 {}%"
interval = 1
on_scroll_up = "pamixer -i 5"
on_scroll_down = "pamixer -d 5"
exec_on_event = true

[layout]
left_section = ["@custom_widget:volume", "workspaces"]
```

Volledige configuratie-opties:

| Sleutel            | Type   | Standaard | Beschrijving                                                               |
| ------------------ | ------ | --------- | -------------------------------------------------------------------------- |
| `id`               | string | —         | Unieke identificatie voor verwijzing in lay-out (`@custom_widget:mijn-id`) |
| `exec`             | string | vereist   | Uit te voeren shell-commando                                               |
| `interval`         | int    | `0`       | Vernieuwingsinterval in seconden (0 = eenmalig uitvoeren)                  |
| `return_type`      | string | `"plain"` | Uitvoerformaat: `"plain"` of `"json"`                                      |
| `label_format`     | string | `"{}"`    | Formaatstring waarbij `{}` wordt vervangen door uitvoer                    |
| `exec_on_event`    | bool   | `false`   | Commando opnieuw uitvoeren na klik/scroll                                  |
| `max_length`       | int    | `0`       | Maximale tekstlengte (0 = geen limiet)                                     |
| `min_length`       | int    | `0`       | Minimale tekstlengte (vult met spaties)                                    |
| `rotate`           | int    | `0`       | Tekst roteren in graden                                                    |
| `tooltip`          | bool   | `true`    | Tooltip tonen met uitvoer                                                  |
| `tooltip_format`   | string | —         | Tooltip-formaatstring                                                      |
| `on_click`         | string | —         | Linksklik-commando                                                         |
| `on_click_right`   | string | —         | Rechtsklik-commando                                                        |
| `on_click_middle`  | string | —         | Middelste klik-commando                                                    |
| `on_scroll_up`     | string | —         | Scroll-omhoog-commando                                                     |
| `on_scroll_down`   | string | —         | Scroll-omlaag-commando                                                     |
| `signal`           | int    | —         | Signaalnummer voor sig* gebeurtenistriggers                                |
| `restart_interval` | int    | —         | Herstartinterval voor persistente scripts                                  |

## Widget Groepen

Groepeer widgets met gedeelde spatiering en stijl:
Verwijs naar een groep in uw lay-out met `@group:N` (nulgebaseerde index) of `@group:id` (tekst-ID):

```toml
[[widget_groups]]
id = "sys-group"
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

Verwijs in de lay-out met `@group:sys-group`.

```toml
[layout]
right_section = ["@group:sys-group", "system_tray"]
```

## Inklapbare Groepen

Verberg minder gebruikte widgets achter een schakelaar:

```toml
[[collapsible_groups]]
id = "utility-tools"
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
tooltip = "Hulpmiddelen"
style_classes = ["utility-tools"]
```

Verwijs in de lay-out met `@collapsible:utility-tools`.

```toml

right_section = ["@collapsible:utility-tools", "system_tray"]

```

## Aangepaste Knop Groep

Een groep aangepaste opdrachtknoppen. Elke knop in de groep kan worden gerefereerd via `@custom_button:N` of `@custom_button:id`:

```toml
[[widgets.custom_buttons]]
id = "firefox"
command = "firefox"
icon = "󰈹"
label_text = "Firefox"
tooltip_text = "Firefox Browser openen"
label_format = "{icon}"
label = false
tooltip = true

[layout]
left_section = ["@custom_button:firefox"]
```

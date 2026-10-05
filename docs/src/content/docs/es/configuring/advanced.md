---
title: Configuración Avanzada
description: Patrones avanzados de configuración de Tsumiki
---

Una vez que te sientas cómodo con los conceptos básicos de [Configuración](/es/configuring/config), estos patrones te ayudarán a ajustar Tsumiki aún más.

## Widget Personalizado

Widgets personalizados compatibles con Waybar que ejecutan comandos shell externos con análisis de salida configurable y manejo de clics.

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

Opciones de configuración completas:

| Clave              | Tipo   | Predeterminado | Descripción                                                                |
| ------------------ | ------ | -------------- | -------------------------------------------------------------------------- |
| `id`               | string | —              | Identificador único para referenciar en el diseño (`@custom_widget:mi-id`) |
| `exec`             | string | requerido      | Comando shell a ejecutar                                                   |
| `interval`         | int    | `0`            | Intervalo de actualización en segundos (0 = ejecutar una vez)              |
| `return_type`      | string | `"plain"`      | Formato de salida: `"plain"` o `"json"`                                    |
| `label_format`     | string | `"{}"`         | Cadena de formato donde `{}` se reemplaza con la salida                    |
| `exec_on_event`    | bool   | `false`        | Re-ejecutar comando después de clic/desplazamiento                         |
| `max_length`       | int    | `0`            | Longitud máxima de texto (0 = sin límite)                                  |
| `min_length`       | int    | `0`            | Longitud mínima de texto (rellena con espacios)                            |
| `rotate`           | int    | `0`            | Rotar texto en grados                                                      |
| `tooltip`          | bool   | `true`         | Mostrar tooltip con la salida                                              |
| `tooltip_format`   | string | —              | Cadena de formato del tooltip                                              |
| `on_click`         | string | —              | Comando de clic izquierdo                                                  |
| `on_click_right`   | string | —              | Comando de clic derecho                                                    |
| `on_click_middle`  | string | —              | Comando de clic medio                                                      |
| `on_scroll_up`     | string | —              | Comando de desplazamiento hacia arriba                                     |
| `on_scroll_down`   | string | —              | Comando de desplazamiento hacia abajo                                      |
| `signal`           | int    | —              | Número de señal para activadores de eventos sig*                           |
| `restart_interval` | int    | —              | Intervalo de reinicio para scripts persistentes                            |

## Grupos de Widgets

Agrupa widgets con espaciado y estilo compartidos:
Referencia un grupo en tu diseño con `@group:N` (índice basado en cero) o `@group:id` (identificador textual) :

```toml
[[widget_groups]]
id = "sys-group"
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

Referencia en el diseño con `@group:sys-group`.

```toml
[layout]
right_section = ["@group:sys-group", "system_tray"]
```

## Grupos Plegables

Oculta widgets menos usados detrás de un alternador:

```toml
[[collapsible_groups]]
id = "utility-tools"
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
label_format = "{icon}"
tooltip = "Utilidades"
style_classes = ["utility-tools"]
```

Referencia en el diseño con `@collapsible:utility-tools`.

```toml

right_section = ["@collapsible:utility-tools", "system_tray"]

```

## Grupo de Botones Personalizados

Un grupo de botones de comando personalizados. Cada botón del grupo se puede referenciar mediante `@custom_button:N` o `@custom_button:id`:

```toml
[[widgets.custom_buttons]]
id = "firefox"
command = "firefox"
icon = "󰈹"
tooltip_text = "Abrir navegador Firefox"
label_format = "{icon}"
tooltip = true

[layout]
left_section = ["@custom_button:firefox"]
```

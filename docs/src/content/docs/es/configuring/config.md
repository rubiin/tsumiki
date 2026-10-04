---
title: Configuración
description: Opciones de configuración de Tsumiki y ajustes de widgets
---

Tsumiki usa TOML para la configuración.

## Archivos de Configuración

- `config.toml`: widgets, diseño, módulos, comportamiento en tiempo de ejecución.
- `tsumiki.schema.json`: esquema fuente de verdad.

:::note
El esquema requiere secciones de `widget_groups` y `collapsible_groups` de nivel superior.
Comenzar desde `example/config.toml` es la forma más segura de mantenerse válido con el esquema.
:::

## Ejemplo de Inicio Rápido

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
tooltip = "Utilidades"
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

## Secciones Principales

### `general`

Comportamiento global como modo de depuración, reinicio automático y controles de múltiples monitores.

| Clave            | Tipo | Predeterminado | Descripción                                |
| ---------------- | ---- | -------------- | ------------------------------------------ |
| `debug`          | bool | `false`        | Activar registro verbose                   |
| `auto_restart`   | bool | `true`         | Reiniciar automáticamente en caso de fallo |
| `restart_delay`  | int  | `1500`         | Retardo antes de reiniciar (ms)            |
| `multi_monitor`  | bool | `false`        | Instancias de barra por monitor            |
| `tooltips`       | bool | `true`         | Activar tooltips de widgets                |
| `check_updates`  | bool | `false`        | Verificar actualizaciones de Tsumiki       |
| `monitor_styles` | bool | `true`         | Vigilar y recargar cambios SCSS            |

### `layout`

Controla la colocación de widgets en las secciones de la barra:

- `left_section`
- `middle_section`
- `right_section`

Cada valor es una lista de IDs de widgets. Usa `@group:N` (índice basado en cero) para grupos de widgets:

```toml
[layout]
left_section = ["@group:0", "window_title"]
middle_section = ["date_time"]
right_section = ["@group:1", "system_tray", "power"]
```

Tipos de referencia disponibles:

| Referencia         | Ejemplo              | Descripción                    |
| ------------------ | -------------------- | ------------------------------ |
| Nombre de widget   | `"workspaces"`       | Referencia directa al widget   |
| `@group:N`         | `"@group:0"`         | Grupo de widgets por índice    |
| `@collapsible:N`   | `"@collapsible:0"`   | Grupo plegable por índice      |
| `@custom_button:N` | `"@custom_button:0"` | Botón personalizado por índice |

### `modules`

Activa y configura módulos de UI más grandes como:

| Módulo               | Clave                    | Descripción                                  |
| -------------------- | ------------------------ | -------------------------------------------- |
| Barra                | `modules.bar`            | Posición y capa del panel                    |
| Notificaciones       | `modules.notification`   | Sistema de notificaciones del escritorio     |
| Dock                 | `modules.dock`           | Dock de aplicaciones con intellihide         |
| Overview             | `modules.overview`       | Vista exposé de espacios de trabajo          |
| OSD                  | `modules.osd`            | Visualización en pantalla para volumen, etc. |
| Lanzador de Apps     | `modules.launcher`       | Búsqueda y lanzamiento de aplicaciones       |
| Reloj de Escritorio  | `modules.desktop_clock`  | Reloj decorativo del escritorio              |
| Citas de Escritorio  | `modules.desktop_quotes` | Superposición de citas inspiradoras          |
| Esquinas de Pantalla | `modules.screen_corners` | Esquinas activas                             |
| Cheatsheet           | `modules.cheatsheet`     | Referencia de atajos de teclado              |
| Activate Linux       | `modules.activate_linux` | Indicador de activación de ventana           |

Ejemplo de configuración del dock:

```toml
[modules.dock]
enabled = true
behavior = "intellihide"
show_when_no_windows = false
icon_size = 40
```

Consulta la [Referencia de Módulos](/es/features/modules) para opciones completas.

### `widgets`

Configuración por widget (iconos, etiquetas, umbrales, intervalos de sondeo, banderas de comportamiento).

Hay más de 45 widgets disponibles. Consulta la [Referencia de Widgets](/es/features/widgets) completa para cada opción.

Los widgets comunes incluyen:

| Widget           | Descripción                       |
| ---------------- | --------------------------------- |
| `workspaces`     | Selector de escritorios virtuales |
| `window_title`   | Título de la ventana activa       |
| `date_time`      | Visualización de fecha/hora       |
| `system_tray`    | Iconos de la bandeja del sistema  |
| `volume`         | Control de volumen de audio       |
| `battery`        | Estado de la batería              |
| `cpu`            | Monitor de uso de CPU             |
| `memory`         | Monitor de uso de memoria         |
| `network_usage`  | Monitor de velocidad de red       |
| `weather`        | Condiciones climáticas            |
| `power`          | Menú de energía (apagado, etc.)   |
| `quick_settings` | Panel de ajustes rápidos          |

## Estilos de Espacios de Trabajo

El widget de espacios de trabajo soporta seis estilos de visualización:

```toml
[widgets.workspaces]
style = "numbered"   # "numbered" | "pill" | "icon" | "minimal" | "underline" | "bubble"
```

- **numbered** — Números con indicador activo en forma de píldora (predeterminado)
- **pill** — Indicadores de píldora mínimos sin texto
- **icon** — Iconos Nerd Font personalizados por espacio de trabajo
- **minimal** — Limpio y sutil con fondo discreto
- **underline** — El espacio de trabajo activo obtiene un borde inferior, sin fondo
- **bubble** — Contenedores de burbuja circulares

## Grupos de Widgets y Grupos Plegables

Agrupa widgets con espaciado y estilo compartidos:

```toml
[[widget_groups]]
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

Los grupos plegables ocultan widgets detrás de un alternador:

```toml
[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
tooltip = "Utilidades"
style_classes = ["utility-tools"]
```

Referencia grupos en el diseño con `@group:N` o `@collapsible:N`.

## Generación de Temas con Matugen

Genera automáticamente paletas de colores desde tu fondo de pantalla:

```toml
[matugen]
enabled = true
wallpaper = "~/Pictures/wallpaper.jpg"
scheme = "scheme-tonal-spot"
mode = "dark"
contrast = 0.0
```

Consulta [Tematización con Matugen](/es/theming/matugen) para más detalles.

## Nota de Migración

Si estás actualizando desde versiones anteriores, revisa [Migración v2 a v3](/es/resources/migration-v2-v3) antes de copiar bloques de configuración antiguos.

## Flujo de Trabajo Recomendado

1. Comienza desde `example/config.toml`.
2. Mantén tu archivo personalizado pequeño y enfocado.
3. Cambia una sección a la vez.
4. Reinicia con `./tsumiki.sh -start` para validar el comportamiento.

## Fuente de Referencia

Esta página es una visión general práctica.
Para definiciones completas de claves y valores predeterminados, consulta la [Referencia de Widgets](/es/features/widgets) y la [Referencia de Módulos](/es/features/modules).
Para el esquema completo, usa `tsumiki.schema.json` en la raíz del proyecto.

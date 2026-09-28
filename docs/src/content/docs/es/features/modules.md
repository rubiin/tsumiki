---
title: Referencia de Módulos
description: Documentación completa de todos los módulos de Tsumiki
sidebar:
  order: 2
---

Los módulos son superficies de UI más grandes que van más allá de la barra, como el dock, las notificaciones, la vista general y el OSD. Se configuran bajo `[modules.<nombre>]` en `config.toml`.

A diferencia de los widgets, la mayoría de los módulos son ventanas independientes o superposiciones que deben activarse explícitamente.

---

## Barra

La barra en sí misma es un módulo. Configura la posición, capa y comportamiento de auto-ocultamiento.

```toml
[modules.bar]
layer = "top"           # "top" | "overlay" | "bottom" | "background"
auto_hide = false
auto_hide_timeout = 3000   # milisegundos
location = "top"           # "top" | "bottom"
```

- **`layer`**: Capa de Hyprland — `top` se renderiza sobre las ventanas, `background` debajo.
- **`auto_hide`**: Oculta la barra después del tiempo de espera cuando no se pasa el cursor.
- **`location`**: Posición de la barra en la pantalla.

---

## Sistema de Notificaciones

Muestra las notificaciones del escritorio a medida que llegan, con apilamiento, agrupación y modo No Molestar.

```toml
[modules.notification]
enabled = true
anchor = "top-right"
auto_dismiss = true
respect_expire = true
dnd_on_screencast = true
ignored = []
transition_type = "slide-left"       # "slide-left" | "slide-right" | "slide-up" | "slide-down" | "crossfade"
transition_duration = 350
per_app_limits = {}
play_sound = false
max_actions = 3
dismiss_on_hover = false
sound_file = "notification4"
max_lines = 4
max_expanded_lines = 20

[modules.notification.timeout]
low = 3000
normal = 8000
critical = 15000

[modules.notification.persist]
enabled = true
low = true
normal = true
critical = true
max_count = 200
```

- **`anchor`**: Posición en pantalla para la ventana de notificaciones.
- **`auto_dismiss`**: Descartar automáticamente las notificaciones después de su tiempo de espera.
- **`respect_expire`**: Respetar el tiempo de expiración del remitente de la notificación.
- **`dnd_on_screencast`**: Activa el modo No Molestar durante la grabación de pantalla.
- **`per_app_limits`**: Limitar notificaciones por aplicación: `{ "app_name": 5 }`.
- **`persist`**: Guardar notificaciones en disco para recuperarlas después de reiniciar.

---

## Dock

Un lanzador de aplicaciones ancladas con intellihide, vistas previas de ventanas y agrupación de aplicaciones.

```toml
[modules.dock]
enabled = false
ignored = []
icon_size = 40
behavior = "intellihide"            # "intellihide" | "always_show"
tooltip = false
layer = "top"
show_when_no_windows = false
s = true
preview_size = [200, 130]
group_apps = true
truncation_size = 20
orientation = "horizontal"
always_show_focused = true
hide_special_workspace_apps = false
show_launcher = true
launcher_position = "last"          # "first" | "last"
ignored = []
```

- **`behavior`**: `intellihide` oculta el dock cuando una ventana se superpone; `always_show` lo mantiene visible.
- **`s`**: Muestra miniaturas de vista previa de ventanas al pasar el cursor.
- **`group_apps`**: Agrupa múltiples ventanas de la misma aplicación.
- **`show_launcher`**: Añade un icono de lanzador de aplicaciones al dock.
- **`hide_special_workspace_apps`**: Oculta aplicaciones en espacios de trabajo especiales (scratchpads).

### Atajos de Teclado

Navega por el dock con:

| Acción                    | Atajo                             |
| ------------------------- | --------------------------------- |
| Enfocar siguiente cliente | `Super+Tab`                       |
| Enfocar cliente anterior  | `Super+Shift+Tab`                 |
| Abrir lanzador            | `Super+Space`                     |
| Mover cliente a espacio   | Clic derecho → "Mover al Espacio" |

---

## Overview (Exposé de Espacios de Trabajo)

Vista general a pantalla completa de todos los espacios de trabajo y sus ventanas.

```toml
[modules.overview]
enabled = false
layer = "top"
anchor = "center"
transition_type = "crossfade"       # "crossfade" | "slide-left" | "slide-right" | "slide-up" | "slide-down"
transition_duration = 350
```

Se abre con un atajo de teclado configurable (predeterminado: `Super+W`). Muestra miniaturas de espacios de trabajo con clic para enfocar.

---

## Lanzador de Aplicaciones

Lanzador de aplicaciones controlado por teclado con búsqueda, diseño de cuadrícula/lista y arrastrar para anclar.

```toml
[modules.launcher]
enabled = false
tooltip = true
icon_size = 35
anchor = "center"
width = 280
height = 320
layout = "grid"                    # "grid" | "list"
grid_columns = 3
grid_spacing = 12
plugins_enabled = true              # comandos slash (/calc, /translate)
plugins_dir = ""                    # predeterminado: <config>/plugins
```

- **`layout`**: `grid` muestra iconos en cuadrícula; `list` los muestra como lista con nombres.
- **`anchor`**: Posición en pantalla (`center`, `top`, `bottom`, etc.).
- **`plugins_enabled`**: Activa los plugins de comandos slash (`/calc`, `/translate`, ...).
- **`plugins_dir`**: Directorio con los plugins Python; por defecto `<config>/plugins`.

### Comandos Slash y Plugins

Escribe `/` para explorar los comandos disponibles o úsalos directamente, p. ej. `/calc 2+2` o `/translate bonjour`. Los plugins se escriben en Python: coloca un archivo `.py` (o un paquete) en `plugins/` y reinicia la barra.

Plugins incluidos:

- **`/calc`** — matemáticas, unidades y moneda mediante libqalculate (`qalc`), p. ej. `/calc 100 cm to inches`.
- **`/translate`** — traducción con idioma de origen automático, p. ej. `/translate bonjour`.
- **`/emoji`** — búsqueda de emojis sin conexión, p. ej. `/emoji rocket`.
- **`/clipboard-history`** — busca en el historial de `cliphist` y copia un elemento, p. ej. `/clipboard-history https://`.
- **`/currency`** — convierte entre monedas con tasas en vivo (Frankfurter, sin clave de API), p. ej. `/currency 100 usd to eur`.
- **`/kill`** — busca procesos en ejecución y termina el seleccionado (SIGTERM, o SIGKILL con `-9`), p. ej. `/kill firefox`. Una consulta numérica se trata como un puerto — `/kill 3000` termina lo que esté escuchando en el puerto 3000.
- **`/search`** — busca en la web (DuckDuckGo, sin clave de API) y abre un resultado en el navegador mientras copia su URL al portapapeles, p. ej. `/search fabric hyprland`.

### Atajos de Teclado

| Acción             | Atajo               |
| ------------------ | ------------------- |
| Abrir lanzador     | `Super+Space`       |
| Navegar            | Teclas de dirección |
| Iniciar aplicación | `Enter`             |
| Cerrar             | `Escape`            |

---

## OSD (Visualización en Pantalla)

Superposiciones transitorias para volumen, brillo y otros ajustes.

```toml
[modules.osd]
enabled = false
timeout = 1500
anchor = "bottom-center"
orientation = "horizontal"
percentage = true
icon_size = 28
transition_type = "slide-up"       # "slide-up" | "slide-down" | "slide-left" | "slide-right" | "crossfade"
transition_duration = 500
osds = ["brightness", "volume"]
```

- **`osds`**: Qué tipos de OSD mostrar. Disponibles: `brightness`, `volume`, `microphone`, `lockkeys`.
- **`percentage`**: Muestra un indicador de porcentaje junto al icono.

---

## Reloj de Escritorio

Una superposición decorativa de reloj en el escritorio (capa inferior).

```toml
[modules.desktop_clock]
enabled = false
type = "cookie"                    # Tipo de widget de reloj
layer = "bottom"
anchor = "bottom-right"
date_format = "%A, %d %B %Y"
time_format = "%H:%M"
nepali_date = false
cookie_size = 230
cookie_sides = 9
cookie_dial_style = "dots"
cookie_hour_hand_style = "fill"
cookie_minute_hand_style = "medium"
cookie_second_hand_style = "dot"
cookie_date_style = "bubble"
cookie_show_seconds = false
cookie_show_hour_marks = false
cookie_background_opacity = 1.0
cookie_widget_scale = 1.0
```

Las opciones `cookie_*` configuran el estilo visual del widget de reloj analógico.

---

## Citas de Escritorio

Muestra citas inspiradoras rotativas en el escritorio.

```toml
[modules.desktop_quotes]
enabled = false
anchor = "bottom-right"
layer = "bottom"
interval = 600      # Segundos entre rotaciones de citas
```

Las citas se obtienen de una API externa.

---

## Activate Linux

Muestra una superposición de indicación de activación de ventana (similar a la vista general de ventanas de GNOME con Alt+Tab).

```toml
[modules.activate_linux]
enabled = false
anchor = "bottom-right"
layer = "bottom"
```

---

## Esquinas de Pantalla

Añade esquinas activas a los bordes de la pantalla.

```toml
[modules.screen_corners]
enabled = false
size = 20
```

---

## Cheatsheet

Una hoja de referencia de atajos de teclado de Hyprland con búsqueda.

Configurado bajo `[widgets.cheatsheet]` — consulta la [Referencia de Widgets](/es/features/widgets) para más detalles.

---

## GUI de Configuración

Una GUI dentro de la aplicación para editar la configuración de Tsumiki.

Se activa desde el widget de Configuración (`[widgets.settings]`). No necesita configuración a nivel de módulo.

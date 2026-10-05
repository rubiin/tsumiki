---
title: Referencia de Widgets
description: Referencia completa de configuración para todos los widgets de Tsumiki
sidebar:
  order: 1
---

Esta página documenta cada widget disponible en Tsumiki, sus opciones de configuración, valores predeterminados y comportamiento.

Los widgets se configuran bajo `[widgets.<nombre>]` en `config.toml` y se colocan en la barra mediante las secciones de `layout`.

---

## Widgets de Información del Sistema

### CPU

Muestra el uso de la CPU con múltiples modos de visualización.

```toml
[widgets.cpu]
label_format = "{icon}"
icon = ""
tooltip = true
round = true
temperature_unit = "celsius"
sensor = "acpitz"
mode = "graph"          # "label" | "graph" | "circular"
graph_length = 4
```

- **`mode`**: Estilo de visualización — `label` muestra texto de porcentaje, `graph` muestra un minigráfico, `circular` muestra un anillo de progreso circular.
- **`graph_length`**: Número de puntos de datos para el minigráfico.
- **`sensor`**: Ruta del sensor de zona térmica (ej. `acpitz`, `k10temp`). Déjalo vacío para detección automática.

### Memoria

Muestra el uso de memoria con múltiples modos de visualización.

```toml
[widgets.memory]
label_format = "{icon}"
icon = ""
tooltip = true
mode = "label"          # "label" | "graph" | "circular"
graph_length = 4
unit = "gb"             # Unidad de visualización para valores de memoria
```

### GPU

Muestra el uso de la GPU (soporta AMD via `amdgpu` y NVIDIA via `nvidia-smi`).

```toml
[widgets.gpu]
label_format = "{icon}"
icon = ""
tooltip = true
mode = "circular"       # "label" | "graph" | "circular"
graph_length = 4
```

### Almacenamiento

Muestra el uso del disco para una ruta dada.

```toml
[widgets.storage]
path = "/"
label_format = "{icon}"
icon = "󰋊"
mode = "label"          # "label" | "graph" | "circular"
tooltip = true
graph_length = 4
unit = "gb"
```

### Uso de Red

Monitorea velocidades de subida/bajada de red en tiempo real.

```toml
[widgets.network_usage]
tooltip = true
label_format = "{upload}   {download} "
upload_threshold = 1024
download_threshold = 1024
kb_digits = 0
mb_digits = 2
interval = 2000         # Intervalo de sondeo en milisegundos
```

Variables disponibles en `label_format`: `{upload}`, `{download}`.

### Actualizaciones

Verifica actualizaciones de paquetes del sistema (Arch Linux, Flatpak, Snap, Homebrew).

```toml
[widgets.updates]
label_format = "{icon} {total}"
pad_zero = true
available_icon = "󰏗"
no_updates_icon = "󰏖"
os = "arch"
interval = 3600         # Intervalo de actualización en segundos
tooltip = true
terminal = "kitty"
auto_hide = false
flatpak = true
snap = false
brew = false
```

- **`label_format`**: Variables disponibles: `{icon}`, `{total}` (el número de actualizaciones).
- **`pad_zero`**: Rellena `{total}` con ceros a dos dígitos (`05`); el cero se muestra como `0`.
- **`interval`**: Intervalo de sondeo en segundos (predeterminado: 3600 = 1 hora).
- **`os`**: Distribución para verificación de paquetes nativos (soporta `arch`, `fedora`, `ubuntu`).
- **`flatpak`/`snap`/`brew`**: Activar verificación para estos formatos de paquetes.

---

## Widgets de Hardware y Energía

### Batería

Muestra el nivel de batería con notificaciones.

```toml
[widgets.battery]
full_battery_level = 100
hide_percent_when_full = true
hide_when_missing = true
tooltip = true
label_format = "{icon} {percent}"

[widgets.battery.notifications]
low_threshold = 10
full_battery = false
low_battery = false
charging = false
```

Variables disponibles en `label_format`: `{icon}`, `{percent}`, `{time_remaining}`.

La sección de notificaciones controla qué eventos de batería activan notificaciones de escritorio.

### Volumen

Controla el volumen de salida de audio del sistema.

```toml
[widgets.volume]
tooltip = true
step_size = 5
```

Haz clic para silenciar/activar sonido, desplázate para ajustar el volumen.

### Brillo

Controla el brillo de la pantalla y el teclado.

```toml
[widgets.brightness]
tooltip = true
step_size = 5
```

Requiere `brightnessctl`. Haz clic para alternar, desplázate para ajustar.

### Bluetooth

Gestiona conexiones y visibilidad Bluetooth.

```toml
[widgets.bluetooth]
label_format = "{icon}"
tooltip = true
```

Abre un popover para gestionar dispositivos emparejados y activar/desactivar Bluetooth.

### Micrófono

Muestra el estado del micrófono y la opción de silenciar.

```toml
[widgets.microphone]
tooltip = true
label_format = "{icon}"
```

Haz clic para silenciar/activar el micrófono.

### Botón de Energía

Menú de energía del sistema con apagado, reinicio, suspensión, hibernación, bloqueo y cierre de sesión.

```toml
[widgets.power]
icon = "󰐥"
tooltip = true
items_per_row = 3
icon_size = 100
label_format = "{icon}"
confirm = true

[widgets.power.item_shortcuts]
shutdown = "s"
reboot = "r"
hibernate = "h"
suspend = "u"
lock = "l"
logout = "o"

[widgets.power.buttons]
shutdown = "systemctl poweroff"
reboot = "systemctl reboot"
hibernate = "systemctl hibernate"
suspend = "systemctl suspend"
lock = "loginctl lock-session"
logout = "loginctl terminate-user $USER"
```

- **`confirm`**: Muestra un diálogo de confirmación antes de ejecutar acciones de energía.
- **`item_shortcuts`**: Atajos de teclado para los elementos del menú de energía.

### Hypridle

Activa/desactiva el daemon de gestión de inactividad de Hyprland.

```toml
[widgets.hypridle]
enabled_icon = ""
label_format = "{icon}"
disabled_icon = ""
tooltip = true
```

### Hyprsunset

Activa/desactiva el filtro de luz azul (modo nocturno) mediante Hyprsunset.

```toml
[widgets.hyprsunset]
temperature = "2800k"
enabled_icon = "󱩌"
label_format = "{icon}"
disabled_icon = "󰛨"
tooltip = true
```

### Hyprpicker

Selector de color que captura un color de la pantalla.

```toml
[widgets.hyprpicker]
icon = ""
tooltip = true
quiet = false
label_format = "{icon}"
```

El color seleccionado se copia al portapapeles. En modo silencioso, no se muestra ninguna notificación.

---

## Widgets de Escritorio y Espacios de Trabajo

### Espacios de Trabajo

Muestra escritorios virtuales con cambio por clic/desplazamiento. Consulta la [documentación completa de Espacios de Trabajo](/es/features/workspaces) para detalles.

```toml
[widgets.workspaces]
count = 10
hide_unoccupied = true
ignored = [-99]
reverse_scroll = false
style = "numbered"       # "numbered" | "pill" | "icon" | "default" | "underline" | "bubble"
empty_scroll = false
label_format = "{id}"
icon_map = {}
show_special = false
show_urgent = false
```

- **`style`**: Elige entre `numbered`, `pill`, `icon`, `default`, `underline` o `bubble`.
- **`icon_map`**: Mapea IDs de espacios de trabajo a iconos personalizados: `{ "1": "", "2": "" }`.- **`label_format`**: Cadena de formato con variable `{id}`.
- **`show_special`**: Mostrar espacios de trabajo especiales (IDs negativos). Establecer en `false` para ocultarlos.
- **`show_urgent`**: Mostrar animación de pulso y color en espacios de trabajo con ventanas urgentes. Establecer en `false` para desactivar.

### Título de Ventana

Muestra el título de la ventana actualmente enfocada.

```toml
[widgets.window_title]
icon = true
truncation = true
truncation_size = 50
tooltip = true
mappings = true
title_map = []
fallback = "class"       # "class" | "title"
```

- **`title_map`**: Lista de reglas de mapeo para renombrar títulos de ventana.
- **`fallback`**: Qué mostrar cuando no hay título disponible.

### Conteo de Ventanas

Muestra el número de ventanas en el espacio de trabajo actual.

```toml
[widgets.window_count]
label_format = " [{count}]"
hide_when_zero = true
tooltip = true
```

Variables disponibles en `label_format`: `{count}`.

### Botón de Overview

Botón que abre la vista general/exposé de ventanas.

```toml
[widgets.overview_button]
icon = "󰡃"
label_format = "{icon}"
tooltip = true
```

### Barra de Tareas

Muestra las aplicaciones en ejecución como iconos en los que se puede hacer clic, similar a una barra de tareas tradicional.

```toml
[widgets.taskbar]
icon_size = 22
ignored = []
tooltip = true
show_current_workspace_only = false
```

---

## Widgets de Fecha, Hora y Calendario

### Menú de Fecha y Hora

Muestra la fecha/hora actual con un popover de calendario y notificaciones de eventos.

```toml
[widgets.date_time]
date_format = " %a %b %d,"
calendar = true
clock_format = "12h"   # "12h" | "24h"
hover_reveal = false
reveal_duration = 500

[widgets.date_time.notification]
enabled = true
count = true
hide_count_on_zero = true
```

### Reloj Mundial

Muestra la hora en múltiples zonas horarias.

```toml
[widgets.world_clock]
icon = "󰃰"
use_24hr = true
label_format = "{icon}"
timezones = ["America/New_York", "Asia/Tokyo"]
```

---

## Widgets de Medios y Audio

### Controles Multimedia MPRIS

Muestra los medios que se están reproduciendo actualmente con controles de reproducción.

```toml
[widgets.mpris]
truncation_size = 20
tooltip = true
label_format = "{title} - {artist}"
hide_when_no_player = true
ignore = []
```

Variables disponibles en `label_format`: `{title}`, `{artist}`, `{album}`, `{name}`.

Requiere `playerctl`. Se oculta automáticamente cuando no hay ningún reproductor de medios en ejecución.

### Visualizador de Audio Cava

Visualización de audio en tiempo real impulsada por Cava.

```toml
[widgets.cava]
bars = 10
color = "#89b4fa"
```

Requiere que Cava esté instalado y configurado.

---

## Utilidades del Sistema

### Captura de Pantalla

Captura pantallas con soporte de anotaciones.

```toml
[widgets.screenshot]
path = "Pictures/Screenshots"
icon = "󰄀"
label_format = "{icon}"
tooltip = true
annotation = true
delayed = false
delayed_timeout = 5000
capture_sound = false
```

Usa `grimblast` para capturas y `satty` para anotaciones.

### Grabación de Pantalla

Inicia/detiene la grabación de pantalla con audio opcional.

```toml
[widgets.recorder]
path = "Videos/Screencasting"
tooltip = true
audio = true
delayed = false
delayed_timeout = 5000
```

Usa `wf-recorder` para grabar.

### OCR (Reconocimiento Óptico de Caracteres)

Extrae texto de una región de la pantalla usando Tesseract.

```toml
[widgets.ocr]
icon = "󰐳"
tooltip = true
label_format = "{icon}"
quiet = false
```

Requiere `tesseract`, `slurp` e `imagemagick`.

### Gestor de Portapapeles

Historial del portapapeles con soporte de imágenes.

```toml
[widgets.clipboard]
icon = ""
label_format = "{icon}"
tooltip = true
item_tooltip = false
show_images = true
enable_pinning = true
```

Usa `cliphist` para el historial del portapapeles.

### Gestor USB

Gestiona el montaje y expulsión de unidades USB.

```toml
[widgets.usb_manager]
icon = "󰕓"
label_format = "{icon}"
tooltip = true
```

---

## Widgets de Entrada e Idioma

### Diseño de Teclado

Muestra el diseño de teclado actual.

```toml
[widgets.keyboard]
icon = "󰌌"
tooltip = true
label_format = ""
```

### Idioma

Muestra el idioma de entrada actual.

```toml
[widgets.language]
icon = ""
tooltip = true
truncation_size = 2
label_format = ""
```

### Submapa

Muestra el submapa de atajos de Hyprland activo.

```toml
[widgets.submap]
icon = "󰌌"
tooltip = true
label_format = ""
hide_on_default = false
```

Se oculta automáticamente cuando el submapa activo es el predeterminado.

---

## Widgets de UI y Aplicaciones

### Botón de Lanzador de Aplicaciones

Abre el popup del lanzador de aplicaciones.

```toml
[widgets.launcher_button]
icon = "view-app-grid-symbolic"
icon_size = 20
tooltip = true
```

### Ajustes Rápidos

Un panel completo de ajustes rápidos con información de usuario, controles, medios y atajos.

```toml
[widgets.quick_settings]
hover_reveal = false

[widgets.quick_settings.user]
avatar = "~/.face"
name = "system"
distro_icon = true

[widgets.quick_settings.controls]
sliders = ["brightness", "volume"]

[widgets.quick_settings.media]
enabled = true
ignore = []
truncation_size = 30
show_album = true
show_artist = true
show_time = true
show_time_tooltip = true

[widgets.quick_settings.shortcuts]
enabled = true

[[widgets.quick_settings.shortcuts.items]]
icon = ""
label = "Terminal"
command = "kitty"
tooltip = "Abrir terminal"
icon_size = 18
```

### Bandeja del Sistema

Bandeja del sistema para aplicaciones en segundo plano (NetworkManager, Bluetooth, etc.).

```toml
[widgets.system_tray]
icon_size = 16
ignored = []
hidden = []
hide_when_empty = false
```

### Botón de Fondo de Pantalla

Abre el popup de selección de fondo de pantalla.

```toml
[widgets.wallpaper]
icon = "󰸉"
label_format = "{icon}"
tooltip = true
```

### Botón de Configuración

Abre la GUI de configuración de la aplicación.

```toml
[widgets.settings]
icon = "󰒓"
tooltip = true
```

### Selector de Temas

Cambia rápidamente entre temas instalados.

```toml
[widgets.theme_switcher]
icon = ""
notify = false    # Mostrar notificación al cambiar de tema
```

### Cheatsheet

Muestra una hoja de referencia de atajos de Hyprland con búsqueda.

```toml
[widgets.cheatsheet]
label_format = "{icon}"
tooltip = true
title = "Hyprland Cheatsheet"
columns = 3
groups_per_page = 6
max_entries_per_group = 8
```

### Selector de Emojis

Busca e inserta caracteres emoji.

```toml
[widgets.emoji_picker]
icon = ""
label_format = "{icon}"
tooltip = true
per_row = 9
per_column = 4
```

### Tablero Kanban

Un tablero simple de gestión de tareas Kanban.

```toml
[widgets.kanban]
icon = "󱞁"
label_format = "{icon}"
tooltip = true
```

### Temporizador Pomodoro

Un temporizador de productividad Pomodoro.

```toml
[widgets.pomodoro]
icon = "🍅"
label_format = "{icon}"
tooltip = true
```

### Acompañante Git

Muestra información del repositorio de GitHub (issues, PRs).

```toml
[widgets.github_tray]
icon = ""
label_format = "{icon}"
tooltip = true
username = "rubiin"
max_repos = 10
avatar_size = 44
default_tab = "issues"      # "issues" | "pull_requests"
cache_ttl = 300
```

### Cloudflare WARP

Gestiona la conexión VPN de Cloudflare WARP — conectar, desconectar y ver estado.

```toml
[widgets.cloudflare_warp]
label_format = "{icon}"
tooltip = true
connected_icon = ""
disconnected_icon = ""
```

- **connected_icon** / **disconnected_icon**: Iconos Nerd Font mostrados en la barra para cada estado.
- Haz clic en el widget para abrir un popover con un botón de alternancia.
- Requiere `warp-cli` de [Cloudflare WARP Client para Linux](https://developers.cloudflare.com/warp-client/get-started/linux/).
- El servicio sondea `warp-cli status` cada 5 segundos para detectar cambios de estado.

### Conmutador DNS

Cambia rápidamente entre proveedores DNS populares directamente desde la barra.

```toml
[widgets.dns_switcher]
icon = "󰚘"
label_format = "{icon}"
tooltip = true
```

Haz clic para abrir un popover con proveedores preconfigurados:

| Proveedor  | DNS Primario     | DNS Secundario    |
| ---------- | ---------------- | ----------------- |
| Cloudflare | `1.1.1.1`        | `1.0.0.1`         |
| Google     | `8.8.8.8`        | `8.8.4.4`         |
| OpenDNS    | `208.67.222.222` | `208.67.220.220`  |
| AdGuard    | `94.140.14.14`   | `94.140.15.15`    |
| Quad9      | `9.9.9.9`        | `149.112.112.112` |

Incluye un botón "Restablecer a Predeterminado (ISP)" para restaurar el DNS automático.

- Usa `nmcli` (NetworkManager) para gestionar la configuración DNS.
- Los cambios DNS requieren autenticación Polkit (`pkexec`).
- El servicio sondea `nmcli` cada 3 segundos para detectar el servidor DNS actual.

### Monitor de IP

Muestra la dirección IP actual.

```toml
[widgets.ip_monitor]
icon = "󰖟"
label_format = "{icon}"
tooltip = true
```

### Cronómetro

Un simple cronómetro/temporizador.

```toml
[widgets.stopwatch]
stopped_icon = "󱫞"
running_icon = "󱫠"
```

### Contador de Clics

Un contador que se incrementa con cada clic.

```toml
[widgets.click_counter]
count = 0
```

### Respira

Un widget guía de ejercicios de respiración.

```toml
[widgets.breathe]
icon = ""
tooltip = true
```

### Clima

Muestra las condiciones climáticas actuales para una ubicación.

```toml
[widgets.weather]
location = "kathmandu"
label_format = "{temperature} {condition}"
tooltip = true
expanded = true
temperature_unit = "celsius"   # "celsius" | "fahrenheit"
wind_speed_unit = "kmh"        # "kmh" | "mph" | "ms" | "beaufort"
interval = 86400
hover_reveal = true
reveal_duration = 500
provider = "open-meteo"        # "open-meteo" | "wttr"
```

Variables disponibles en `label_format`: `{temperature}`, `{condition}`.

---

## Widgets de Diseño y Agrupación

### Divisor

Un separador visual entre secciones de la barra.

```toml
[widgets.divider]
size = 2
```

### Botón Personalizado

Consulta la [Configuración Avanzada](/es/configuring/advanced) para configuración y uso.

### Grupo de Botones Personalizados

Consulta la [Configuración Avanzada](/es/configuring/advanced) para configuración y uso.

### Widget Personalizado

Consulta la [Configuración Avanzada](/es/configuring/advanced) para configuración y uso.

## Grupos de Widgets y Grupos Plegables

Los widgets se pueden agrupar con estilo compartido:

```toml
[[widget_groups]]
widgets = ["workspaces", "window_title"]
spacing = 2
style_classes = ["compact"]

[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
label_format = "{icon}"
tooltip = "Utilidades"
style_classes = ["utility-tools"]
```

Referencia grupos en el diseño usando `@group:N` o `@collapsible:N` (índice basado en cero):

```toml
[layout]
left_section = ["@group:0", "window_title"]
right_section = ["@group:1", "@collapsible:0", "system_tray"]
```

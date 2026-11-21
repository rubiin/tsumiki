---
title: Architecture
description: Tsumiki architecture overview for developers and contributors
sidebar:
  order: 5
---

This page describes Tsumiki's internal architecture — useful for contributors, custom widget authors, and anyone extending the project.

## Project Structure

```
tsumiki/
├── main.py                  # Application entry point
├── config.toml              # User configuration
├── tsumiki.schema.json      # JSON Schema for validation
├── tsumiki.sh                  # Setup/start utilities
├── install.sh               # Bootstrap installer
├── themes/                  # Theme .toml files
│   ├── catpuccin-mocha.toml
│   ├── gruvbox.toml
│   └── ...
├── styles/                  # SCSS stylesheets
│   ├── main.scss            # Entry point — imports everything
│   ├── _theme.scss          # Generated theme variables
│   ├── _settings.scss       # Generated config variables
│   ├── _variable.scss       # Shared variable definitions
│   ├── _workspace.scss      # Per-widget styles
│   └── common/              # Shared mixins & functions
├── widgets/                 # Bar widgets (panel elements)
│   ├── workspaces.py
│   ├── battery.py
│   └── ...                  # ~45 widgets total
├── modules/                 # Standalone overlays & windows
│   ├── bar.py               # Bar window
│   ├── dock.py              # Dock
│   ├── notification.py      # Notification system
│   ├── overview.py          # Workspace overview
│   └── ...
├── services/                # Background services
│   ├── battery.py           # UPower D-Bus monitoring
│   ├── network.py           # NetworkManager D-Bus
│   ├── matugen.py           # Material You color generation
│   ├── mpris.py             # Media player control
│   └── ...
├── shared/                  # Reusable UI components
│   ├── widget_container.py  # Base widget class
│   ├── buttons.py           # Reusable button types
│   ├── popup.py             # Popup window helper
│   ├── popover.py           # Popover menu helper
│   └── ...
├── utils/                   # Utility modules
│   ├── config.py            # Config loading & parsing
│   ├── constants.py         # Default values & paths
│   ├── widget_settings.py   # TypedDict definitions
│   ├── functions.py         # Shared helper functions
│   └── ...
└── assets/                  # Static assets
    ├── icons/               # Icon files
    ├── sounds/              # Notification sounds
    ├── i18n/                # Internationalization
    └── matugen/             # Matugen config template
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    main.py                           │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐ │
│  │ Config    │  │ CSS      │  │ Module Init       │ │
│  │ Loader   │──│ Compiler │──│ (dock, overview,   │ │
│  │           │  │ (sass)   │  │  notifications)   │ │
│  └──────────┘  └──────────┘  └───────────────────┘ │
└──────────────────────┬──────────────────────────────┘
                       │
      ┌────────────────┼────────────────┐
      ▼                ▼                ▼
┌──────────┐    ┌──────────┐    ┌──────────┐
│ Services │    │ Widgets  │    │ Modules  │
│ (DBus,   │───▶│ (Panel   │───▶│ (Overlay │
│  polling)│    │  buttons)│    │  windows)│
└──────────┘    └──────────┘    └──────────┘
```

## Key Design Patterns

### Signal-Driven Updates

Most widgets update via signals (GTK or custom Service signals) rather than polling:

```python
# Service emits signal on state change
self.battery_service.connect("changed", self._on_battery_changed)
```

This keeps CPU usage low — widgets only update when their data changes.

### Singleton Services

Services are singletons initialized at startup:

```python
from services.base import SingletonService


class BatteryService(SingletonService):
    # Single instance shared across all widgets
    pass


battery_service = BatteryService()
```

### Widget Lifecycle

Every widget in the bar follows this lifecycle:

1. **Instantiation** — `__init__` reads config, sets up UI
2. **Connection** — connects to service signals
3. **Update** — reacts to data changes via signal handlers
4. **Cleanup** — disconnects signals and stops timers on destroy

### Popover Pattern

Widgets with popover menus use the `PopoverMixin`:

```python
from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget


class MyWidget(ButtonWidget, PopoverMixin):
    def __init__(self, **kwargs):
        super().__init__(name="my_widget", **kwargs)
        self.setup_popover(lambda: MyPopoverContent(parent=self))
```

## Services Reference

| Service             | File                              | Source                 | Description                     |
| ------------------- | --------------------------------- | ---------------------- | ------------------------------- |
| Battery             | `services/battery.py`             | UPower D-Bus           | Battery level, charging state   |
| Disks               | `services/disks.py`               | UDisks2 D-Bus          | Filesystem discovery, mount     |
| Network             | `services/network.py`             | NetworkManager D-Bus   | WiFi, Ethernet, signal strength |
| Brightness          | `services/brightness.py`          | brightnessctl          | Screen/keyboard brightness      |
| Weather             | `services/weather.py`             | Open-Meteo / wttr.in   | Weather conditions, forecast    |
| MPRIS               | `services/mpris.py`               | Playerctl D-Bus        | Media playback, track info      |
| Screen Record       | `services/screen_record.py`       | wf-recorder, grimblast | Recording, screenshots          |
| Matugen             | `services/matugen.py`             | matugen binary         | Material You palette generation |
| Network Speed       | `services/networkspeed.py`        | /proc/net              | Real-time bandwidth monitoring  |
| Quotes              | `services/quotes.py`              | External API           | Inspirational quotes            |
| Custom Notification | `services/custom_notification.py` | —                      | Programmatic notification API   |

## Shared Components

| Component          | File                                  | Purpose                                 |
| ------------------ | ------------------------------------- | --------------------------------------- |
| `ButtonWidget`     | `shared/widget_container.py`          | Base class for all panel button widgets |
| `PopoverMixin`     | `shared/mixins.py`                    | Mixin for popover/show-hide behavior    |
| `AnimatedScale`    | `shared/animated/scale.py`            | Animated slider scale                   |
| `CircularProgress` | `shared/animated/circularprogress.py` | Circular progress ring widget           |
| `ButtonToggle`     | `shared/button_toggle.py`             | Toggle button with on/off icons         |
| `CollapsibleGroup` | `shared/collapsible_group.py`         | Collapsible widget group container      |
| `MediaPlayer`      | `shared/media.py`                     | Reusable MPRIS media player UI          |
| `Submenu`          | `shared/submenu.py`                   | Slide-in submenu panel                  |
| `TagEntry`         | `shared/tagentry.py`                  | Tag/chip input field                    |
| `LottieAnimation`  | `shared/lottie.py`                    | Lottie/rlottie animation player         |

## Adding a New Widget

1. Create `widgets/my_widget.py` extending `ButtonWidget` (and optionally `PopoverMixin`)
2. Add configuration TypedDict in `utils/widget_settings.py`
3. Add default config in `utils/constants.py`
4. Add schema entry in `tsumiki.schema.json`
5. Register in `modules/bar.py` widget map
6. Add SCSS styles in `styles/_my_widget.scss`
7. Reference in layout: `left_section = ["my_widget"]`

## Adding a New Module

1. Create `modules/my_module.py` as a GTK Window
2. Add config under `[modules.my_module]`
3. Initialize in `main.py`
4. Add schema entry in `tsumiki.schema.json`
5. Add SCSS styles

## Validation & Schema

Config validation happens at startup through `tsumiki.schema.json`:

```python
from utils.validation import validate_config_enums

validate_config_enums(config_data, "tsumiki.schema.json")
```

The schema validates:

- Enum values (e.g., workspace style, widget mode)
- Type correctness
- Required fields

Widget references in layout sections are also validated — unknown widget names raise clear errors.

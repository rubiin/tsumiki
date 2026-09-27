
text_nerd_icons = {
    "ui": {
        "window_close": "",
        "question": "",
        "headset": "󰋎",
        "headphones": "󰋋",
        "phone": "󰏲",
        "watch": "",
        "keyboard": "",
        "mouse": "",
        "tv": "",
        "printer": "󰐪",
        "camera": "",
        "speakers": "󰓃",
        "package": "",
        "tick": "",
        "fold": "",
        "lock": "",
        "refresh": "",
    },
    "ethernet": "󰈀",
    "wifi": {
        "connected": "󰤨",
        "disconnected": "󰤩",
        "connecting": "󰤪",
        "disabled": "󰤭",
        "generic": "󰤬",
        "strength_0": "󰤯",
        "strength_1": "󰤟",
        "strength_2": "󰤢",
        "strength_3": "󰤥",
        "strength_4": "󰤨",
    },
    "idle": {
        "enabled": "",
        "disabled": "",
    },
    "mpris": {
        "playing": "",
        "paused": "",
        "stopped": "",
        "previous": "",
        "next": "",
        "shuffle": "",
        "loop": "",
    },
    "trash": {
        "full": "",
        "empty": "",
        "full_filled": "",
    },
    "notifications": {
        "noisy": "󰂜",
        "full": "󰅸",
        "silent": "󰪑",
        "checked": "󱇥",
    },
    "chevron": {
        "right": "",
        "left": "",
        "down": "",
        "up": "",
    },
    "nightlight": {
        "enabled": "󱩌",
        "disabled": "󰛨",
    },
    "bluetooth": {"enabled": "󰂱", "disabled": "󰂲"},
    "flight": {"enabled": "󰗕", "disabled": "󰗔"},
    "color": {"dark": "󰖔", "light": "󰖙"},
    "power_menu": {
        "shutdown": "󰐥",
        "reboot": "",
        "suspend": "󰒂",
        "hibernate": "󰒂",
    },
    "cpu": "",
    "memory": "",
    "storage": "󰋊",
    "updates": "󱧘",
    "thermometer": "",
    "recorder": "󰻂",
    "fallback": "",
    "battery": {
        "charging": "󰠠",
        "low": "󰂎",
    },
    "hourglass": "",
    "powerprofiles": {"power-saver": "󰌪", "performance": "󰓅", "balanced": "󰒂"},
    "volume": {
        "overamplified": "󱄠",
        "high": "󰕾",
        "medium": "󰖀",
        "low": "󰕿",
        "muted": "󰝟",
    },
    "microphone": {
        "muted": "",
        "low": "󰖁",
        "medium": "󰖂",
        "high": "",
    },
    "brightness": {
        "off": "󰃞",
        "low": "󰃝",
        "medium": "󰃟",
        "high": "󰃠",
    },
    "distro": {
        "deepin": "",
        "fedora": "",
        "arch": "",
        "nixos": "",
        "debian": "",
        "opensuse-tumbleweed": "",
        "ubuntu": "",
        "endeavouros": "",
        "manjaro": "",
        "popos": "",
        "garuda": "",
        "zorin": "",
        "mxlinux": "",
        "arcolinux": "",
        "gentoo": "",
        "artix": "",
        "centos": "",
        "hyperbola": "",
        "kubuntu": "",
        "mandriva": "",
        "xerolinux": "",
        "parabola": "",
        "void": "",
        "linuxmint": "",
        "archlabs": "",
        "devuan": "",
        "freebsd": "",
        "openbsd": "",
        "slackware": "",
    },
}


def get_path(d, path, sep=".", fallback=""):
    for key in path.split(sep):
        # An icon name can be deeper than the tree, so a leaf is a miss, not a crash.
        if not isinstance(d, dict):
            return fallback
        d = d.get(key, {})
    return d or fallback


def get_text_icon(name: str, fallback: str = "") -> str:
    return get_path(text_nerd_icons, name, fallback=fallback)


network_icon_to_text_icons = {
    "network-wireless-signal-excellent-symbolic": get_text_icon("wifi.strength_4", "󰤨"),
    "network-wireless-signal-good-symbolic": get_text_icon("wifi.strength_3", "󰤥"),
    "network-wireless-signal-ok-symbolic": get_text_icon("wifi.strength_2", "󰤢"),
    "network-wireless-signal-weak-symbolic": get_text_icon("wifi.strength_1", "󰤟"),
    "network-wireless-signal-none-symbolic": get_text_icon("wifi.strength_0", "󰤯"),
}

symbolic_icons = {
    "missing": "image-missing-symbolic",
    "nix": {
        "nix": "nix-snowflake-symbolic",
    },
    "app": {
        "terminal": "terminal-symbolic",
    },
    "fallback": {
        "executable": "application-x-executable",
        "notification": "dialog-information-symbolic",
        "video": "video-x-generic-symbolic",
        "audio": "audio-x-generic-symbolic",
        "image": "image-x-generic-symbolic",
        "package": "package-x-generic-symbolic",
    },
    "ui": {
        "window_close": "window-close-symbolic",
        "close": "close-symbolic",
        "colorpicker": "color-select-symbolic",
        "info": "info-symbolic",
        "link": "external-link-symbolic",
        "lock": "system-lock-screen-symbolic",
        "menu": "open-menu-symbolic",
        "refresh": "view-refresh-symbolic",
        "search": "system-search-symbolic",
        "settings": "emblem-system-symbolic",
        "themes": "preferences-desktop-theme-symbolic",
        "tick": "object-select-symbolic",
        "time": "hourglass-symbolic",
        "toolbars": "toolbars-symbolic",
        "warning": "dialog-warning-symbolic",
        "avatar": "avatar-default-symbolic",
        "camera": "camera-photo-symbolic",
        "camera-video": "camera-video-symbolic",
        "arrow": {
            "right": "pan-end-symbolic",
            "left": "pan-start-symbolic",
            "down": "pan-down-symbolic",
            "up": "pan-up-symbolic",
        },
    },
    "audio": {
        "mic": {
            "muted": "microphone-disabled-symbolic",
            "low": "microphone-sensitivity-low-symbolic",
            "medium": "microphone-sensitivity-medium-symbolic",
            "high": "microphone-sensitivity-high-symbolic",
        },
        "volume": {
            "muted": "audio-volume-muted-symbolic",
            "low": "audio-volume-low-symbolic",
            "medium": "audio-volume-medium-symbolic",
            "high": "audio-volume-high-symbolic",
            "overamplified": "audio-volume-overamplified-symbolic",
        },
        "type": {
            "headset": "audio-headphones-symbolic",
            "speaker": "audio-speakers-symbolic",
            "card": "audio-card-symbolic",
        },
        "mixer": "mixer-symbolic",
    },
    "powerprofiles": {
        "balanced": "power-profile-balanced-symbolic",
        "power-saver": "power-profile-power-saver-symbolic",
        "performance": "power-profile-performance-symbolic",
    },
    "battery": {
        "charging": "battery-flash-symbolic",
        "full": "battery-full-charged-symbolic",
        "full-charging": "battery-full-charging-symbolic",
        "full-discharging": "battery-full-discharging-symbolic",
        "discharging": "battery-empty-symbolic",
        "empty": "battery-empty-symbolic",
        "charging-unknown": "battery-charging-symbolic",
        "unknown": "battery-missing-symbolic",
    },
    "bluetooth": {
        "enabled": "bluetooth-active-symbolic",
        "disabled": "bluetooth-disabled-symbolic",
    },
    "brightness": {
        "indicator": "display-brightness-symbolic",
        "keyboard": "keyboard-brightness-symbolic",
        "screen": "display-brightness-symbolic",
        "low": "display-brightness-low-symbolic",
        "medium": "display-brightness-medium-symbolic",
        "high": "display-brightness-high-symbolic",
        "off": "display-brightness-off-symbolic",
    },
    "powermenu": {
        "sleep": "system-suspend-symbolic",
        "reboot": "system-reboot-symbolic",
        "logout": "system-log-out-symbolic",
        "shutdown": "system-shutdown-symbolic",
    },
    "recorder": {
        "recording": "media-record-symbolic",
        "stopped": "media-record-symbolic",
    },
    "notifications": {
        "noisy": "org.gnome.Settings-notifications-symbolic",
        "silent": "notifications-disabled-symbolic",
        "message": "chat-bubbles-symbolic",
    },
    "trash": {
        "full": "user-trash-full-symbolic",
        "empty": "user-trash-symbolic",
    },
    "network": {
        "wifi": {
            "generic": "network-wireless-symbolic",
            "connected": "network-wireless-connected-symbolic",
            "disconnected": "network-wireless-disconnected-symbolic",
            "connecting": "network-wireless-acquiring-symbolic",
            "disabled": "network-wireless-disabled-symbolic",
        },
        "ethernet": {
            "connected": "network-wired-connected-symbolic",
            "disconnected": "network-wired-disconnected-symbolic",
            "connecting": "network-wired-acquiring-symbolic",
            "disabled": "network-wired-disabled-symbolic",
        },
        "vpn": {
            "enabled": "network-vpn-symbolic",
            "disabled": "network-vpn-off-symbolic",
        },
    },
    "mpris": {
        "shuffle": {
            "enabled": "media-playlist-shuffle-symbolic",
            "disabled": "media-playlist-consecutive-symbolic",
        },
        "loop": {
            "none": "media-playlist-repeat-symbolic",
            "track": "media-playlist-repeat-song-symbolic",
            "playlist": "media-playlist-repeat-symbolic",
        },
        "playing": "media-playback-pause-symbolic",
        "paused": "media-playback-start-symbolic",
        "stopped": "media-playback-start-symbolic",
        "prev": "media-skip-backward-symbolic",
        "next": "media-skip-forward-symbolic",
    },
    "system": {
        "cpu": "org.gnome.SystemMonitor-symbolic",
        "ram": "drive-harddisk-solidstate-symbolic",
        "temp": "temperature-symbolic",
    },
    "color": {
        "dark": "dark-mode-symbolic",
        "light": "light-mode-symbolic",
    },
}

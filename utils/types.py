# Define the type
from typing import Literal, get_args

Layer = Literal["background", "bottom", "top", "overlay"]


Anchor = Literal[
    "center-left",
    "center",
    "center-right",
    "top",
    "top-right",
    "top-center",
    "top-left",
    "bottom-left",
    "bottom-center",
    "bottom-right",
]


Temperature_Unit = Literal["celsius", "fahrenheit"]

Wind_Speed_Unit = Literal["mph", "kmh"]

Weather_Provider = Literal["open-meteo", "wttr"]

Time_Format = Literal["12h", "24h"]

Keyboard_Mode = Literal["none", "exclusive", "on-demand"]


Power_Options = Literal["shutdown", "reboot", "hibernate", "suspend", "lock", "logout"]

Widget_Mode = Literal["circular", "graph", "label"]


Reveal_Animations = Literal[
    "none", "crossfade", "slide-right", "slide-left", "slide-up", "slide-down"
]

# "auto" opens from the bar edge the popover is anchored to.
Popover_Transition = Literal[
    "auto",
    "none",
    "crossfade",
    "slide-right",
    "slide-left",
    "slide-up",
    "slide-down",
]

Orientation = Literal["vertical", "horizontal"]

Dock_Behavior = Literal["always_show", "intellihide"]

Bar_Location = Literal["top", "bottom"]

Data_Unit = Literal["kb", "mb", "gb", "tb"]

Return_Type = Literal["plain", "json"]

Osd_Type = Literal["brightness", "volume", "microphone"]

Slider_Type = Literal["brightness", "volume", "microphone"]

Title_Fallback = Literal["class", "title"]


# Theme enums
Theme_Scheme = Literal[
    "scheme-tonal-spot",
    "scheme-content",
    "scheme-expressive",
    "scheme-fidelity",
    "scheme-fruit-salad",
    "scheme-monochrome",
    "scheme-neutral",
    "scheme-rainbow",
]

Theme_Mode = Literal["dark", "light"]

Widget_Style = Literal[
    "default",
    "flat",
    "shadow",
    "bordered",
    "leaf",
    "leaf-inverse",
]

Bar_Panel_Style = Literal["default", "floating", "scoop"]

Bar_Widget_Style = Literal[
    "default", "flat", "shadow", "bordered", "leaf", "leaf-inverse"
]


# Helper function to extract values from Literal types
def get_literal_values(literal_type) -> list[str]:
    """Extract the string values from a Literal type."""
    return list(get_args(literal_type))

from fabric.widgets.box import Box
from fabric.widgets.label import Label

from utils.widget_utils import nerd_font_icon

from .mixins import PopoverMixin
from .widget_container import ButtonWidget


class CollapsibleGroupWidget(ButtonWidget, PopoverMixin):
    """A collapsible button group that shows a main toggle button in the bar.

    When clicked, reveals a popup menu with grouped widgets underneath.
    Uses lazy initialization for performance.
    """

    def __init__(self, **kwargs):
        super().__init__(name="collapsible_group", **kwargs)

        # Initialize defaults - will be overridden when config is updated
        self.widgets_config = []
        self.icon_name = "󰍽"  # default icon
        self.show_icon = True
        self.show_label = False
        self.label_text = "Tools"
        self.tooltip_text = "Toggle tool menu"

        self.is_expanded = False
        self.widgets_list = None

        # Read configuration and setup the widget
        self._read_config()
        self._setup_button_content()
        # PopoverMixin owns the popover: it is built on first use from
        # _build_popover_content, and it maintains the "active" class.
        self.setup_popover(self._build_popover_content, connect_clicked=False)
        self.connect("clicked", self.on_toggle_clicked)

    def _read_config(self):
        """Read configuration values from the config."""
        # Fix: Read config directly instead of from non-existent "group" key
        self.widgets_config = self.config.get("widgets", [])
        self.icon_name = self.config.get("icon", "󰍽")
        self.show_icon = self.config.get("show_icon", True)
        self.show_label = self.config.get("show_label", False)
        self.label_text = self.config.get("label", "Tools")
        self.tooltip_text = self.config.get("tooltip", "Toggle tool menu")

    def _setup_button_content(self):
        """Set up the content of the main toggle button."""
        if self.show_icon:
            icon = nerd_font_icon(
                icon=self.icon_name,
                props={"style_classes": ["panel-font-icon"]},
            )
            self.container_box.add(icon)

        if self.show_label:
            label = Label(label=self.label_text, style_classes="panel-text")
            self.container_box.add(label)

    def _build_popover_content(self) -> Box:
        """Build the popover content: the grouped widgets, in a row."""
        self.widgets_box = Box(
            orientation="h",
            spacing=self.config.get("spacing", 4),
            style_classes=[
                "panel-collapsible-group",
                *self.config.get("style_classes", []),
            ],
        )

        self._populate_widgets()
        return self.widgets_box

    def _set_expanded(self, expanded: bool):
        """Sets the expanded state of the widget."""
        if self.is_expanded == expanded:
            return  # No change

        if expanded:
            self.show_popover()
        else:
            self.hide_popover()

        self.is_expanded = expanded

    def on_toggle_clicked(self, button):
        """Handle the toggle button click."""
        self._set_expanded(not self.is_expanded)

    def _populate_widgets(self):
        """Populate the widgets box with configured widgets."""
        if not hasattr(self, "widgets_box") or not hasattr(self, "_resolver_context"):
            return

        # Clear existing widgets
        for child in self.widgets_box.get_children():
            child.destroy()

        # Use the widget factory system
        from utils.widget_factory import WidgetResolver

        # Note: Don't use `self.widgets_list or {}` because LazyWidgetDict
        # inherits from dict but is empty, so it evaluates to falsy
        widgets_list = self.widgets_list if self.widgets_list is not None else {}
        resolver = WidgetResolver(widgets_list)
        widgets = resolver.batch_resolve(self.widgets_config, self._resolver_context)

        for widget in widgets:
            self.widgets_box.add(widget)

        # Show all widgets - required for dynamically added widgets
        self.widgets_box.show_all()

    def set_context(self, config: dict, widgets_list: dict):
        """Set resolution context for widget creation."""
        self._resolver_context = {"config": config}
        self.widgets_list = widgets_list

    def collapse(self):
        """Collapse the group programmatically."""
        self._set_expanded(False)

    def expand(self):
        """Expand the group programmatically."""
        self._set_expanded(True)

    def update_config(self, config_dict):
        """Update the widget configuration and refresh the display."""
        self.config.update(config_dict)
        self._read_config()

        # Clear and rebuild button content with new config
        for child in self.container_box.get_children():
            child.destroy()

        self._setup_button_content()

        if self.tooltips_enabled:
            self.set_tooltip_text(self.tooltip_text)

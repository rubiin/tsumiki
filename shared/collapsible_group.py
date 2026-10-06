from fabric.widgets.box import Box

from .mixins import PopoverMixin
from .widget_container import ButtonWidget


class CollapsibleGroupWidget(ButtonWidget, PopoverMixin):
    """A collapsible button group that shows a main toggle button in the bar.

    Clicking reveals a popup of the grouped widgets, built on first use.
    """

    def __init__(self, **kwargs):
        super().__init__(name="collapsible_group", **kwargs)

        self.widgets_config = []
        self.label_format = "󰍽"
        self.tooltip_text = "Toggle tool menu"

        self.is_expanded = False
        self.widgets_list = None

        # Read configuration and setup the widget
        self._read_config()
        self._setup_button_content()
        # PopoverMixin builds the popover on first use and owns the "active" class.
        self.setup_popover(self._build_popover_content, connect_clicked=False)
        self.connect("clicked", self.on_toggle_clicked)

    def _read_config(self):
        """Read configuration values from the config."""
        self.widgets_config = self.config.get("widgets", [])
        self.label_format = self.config.get("label_format", "󰍽")
        self.tooltip_text = self.config.get("tooltip", "Toggle tool menu")

    def _setup_button_content(self):
        """Set up the content of the main toggle button."""
        self.add_formatted_label(self.label_format)

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
            return

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

        for child in self.widgets_box.get_children():
            child.destroy()

        from utils.widget_factory import WidgetResolver

        # LazyWidgetDict subclasses dict but is empty, so `or {}` would discard it.
        widgets_list = self.widgets_list if self.widgets_list is not None else {}
        resolver = WidgetResolver(widgets_list)
        widgets = resolver.batch_resolve(self.widgets_config, self._resolver_context)

        for widget in widgets:
            self.widgets_box.add(widget)

        # Dynamically added widgets are invisible until show_all.
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

        for child in self.container_box.get_children():
            child.destroy()

        self._setup_button_content()

        if self.tooltips_enabled:
            self.set_tooltip_text(self.tooltip_text)

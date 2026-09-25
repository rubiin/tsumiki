"""
Settings GUI for Tsumiki
"""

from collections.abc import Callable
from typing import Any

from fabric.utils import Gtk, logger
from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.grid import Grid
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.stack import Stack
from fabric.widgets.window import Window

from shared.buttons import HoverButton
from utils.config import configuration, tsumiki_config
from utils.constants import ASSETS_DIR
from utils.functions import send_notification, write_toml_file
from utils.types import (
    Anchor,
    Bar_Location,
    Bar_Panel_Style,
    Bar_Widget_Style,
    Data_Unit,
    Dock_Behavior,
    Layer,
    Orientation,
    Reveal_Animations,
    Temperature_Unit,
    Theme_Mode,
    Theme_Scheme,
    Weather_Provider,
    Widget_Mode,
    Widget_Style,
    get_literal_values,
)


class SettingsGUI(Window):
    """Settings window for Tsumiki configuration."""

    _instance = None
    _visible = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, **kwargs):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True

        super().__init__(
            title="Tsumiki Settings",
            name="settings-window",
            size=(700, 550),
            **kwargs,
        )

        self.set_resizable(False)
        import copy

        self.config = copy.deepcopy(tsumiki_config)
        self.theme = self.config.get("styling", {})
        self.modified = False

        # Main layout
        root_box = Box(orientation="v", spacing=10, style="margin: 10px;")
        self.add(root_box)

        # Content with sidebar
        main_content = Box(
            orientation="h",
            spacing=6,
            v_expand=True,
            h_expand=True,
        )
        root_box.add(main_content)

        # Tab stack
        self.tab_stack = Stack(
            transition_type="slide-up-down",
            transition_duration=250,
            v_expand=True,
            h_expand=True,
        )

        # Create tabs
        self._setup_tabs()

        # Tab switcher (sidebar)
        tab_switcher = Gtk.StackSwitcher()
        tab_switcher.set_stack(self.tab_stack)
        tab_switcher.set_orientation(Gtk.Orientation.VERTICAL)
        tab_switcher.set_name("settings-sidebar")
        main_content.add(tab_switcher)
        main_content.add(self.tab_stack)

        # Button box
        button_box = Box(orientation="h", spacing=10, h_align="end")

        reset_btn = HoverButton(
            label="Reset",
            name="settings-reset-btn",
            on_clicked=self._on_reset,
        )
        button_box.add(reset_btn)

        close_btn = HoverButton(
            label="Close",
            name="settings-close-btn",
            on_clicked=self._on_close,
        )
        button_box.add(close_btn)

        self.save_btn = HoverButton(
            label="Apply & Save",
            name="settings-save-btn",
            on_clicked=self._on_save,
            sensitive=False,
        )
        self.save_btn.set_sensitive(False)
        button_box.add(self.save_btn)

        root_box.add(button_box)

        # Connect close event
        self.connect("delete-event", self._on_delete)

    def _setup_tabs(self):
        """Setup all tabs in the stack."""
        self.tab_stack.add_titled(self._create_general_tab(), "general", "󰒓 General")
        self.tab_stack.add_titled(self._create_layout_tab(), "layout", "󰉯 Layout")
        self.tab_stack.add_titled(self._create_modules_tab(), "modules", "󰒍 Modules")
        self.tab_stack.add_titled(self._create_widgets_tab(), "widgets", "󰕰 Widgets")
        self.tab_stack.add_titled(self._create_theme_tab(), "theme", "󰸌 Theme")
        self.tab_stack.add_titled(self._create_about_tab(), "about", "󰋽 About")

    def _refresh_tabs(self):
        """Refresh all tab contents with current config."""
        current_tab = self.tab_stack.get_visible_child_name()

        for child in self.tab_stack.get_children():
            self.tab_stack.remove(child)

        self._setup_tabs()
        self.tab_stack.set_visible_child_name(current_tab)
        self.show_all()

    def _create_scrolled_container(self) -> tuple[ScrolledWindow, Box]:
        """Create a scrolled window with a vbox inside."""
        vbox = Box(orientation="v", spacing=15, style="margin: 15px;")

        scrolled = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=True,
            v_expand=True,
            propagate_width=False,
            propagate_height=False,
        )
        scrolled.add(vbox)
        return scrolled, vbox

    def _create_section_header(self, text: str) -> Label:
        """Create a section header label."""
        return Label(
            markup=f"<b>{text}</b>",
            h_align="start",
            name="settings-section-header",
        )

    def _create_label(self, text: str) -> Label:
        """Create a standard label for settings."""
        return Label(
            label=text.replace("_", " ").title(),
            h_align="start",
            v_align="center",
            h_expand=True,
        )

    def _create_grid(self, margin_bottom: int = 0) -> Grid:
        """Create a standard grid for settings."""
        return Grid(
            column_spacing=20,
            row_spacing=8,
            margin_start=10,
            margin_top=5,
            margin_bottom=margin_bottom,
            column_homogeneous=False,
        )

    def _create_expander(self, label: str) -> Gtk.Expander:
        """Create a GTK expander for nested settings."""
        expander = Gtk.Expander(label=label, expanded=False, name="settings-expander")
        return expander

    def _create_switch(self, active: bool, on_change=None) -> Gtk.Switch:
        """Create a GTK switch."""
        switch = Gtk.Switch(
            active=active, halign=Gtk.Align.START, valign=Gtk.Align.CENTER
        )
        if on_change:
            switch.connect("notify::active", on_change)
        return switch

    def _create_combo(
        self, options: list, active: str, on_change=None
    ) -> Gtk.ComboBoxText:
        """Create a combo box."""
        combo = Gtk.ComboBoxText(halign=Gtk.Align.START, valign=Gtk.Align.CENTER)
        for opt in options:
            combo.append_text(opt)
        try:
            combo.set_active(options.index(active))
        except ValueError:
            combo.set_active(0)
        if on_change:
            combo.connect("changed", on_change)
        return combo

    def _create_spinbutton(
        self, value, min_val, max_val, on_change=None, step=1, digits=0
    ) -> Gtk.SpinButton:
        """Create a spin button."""
        adj = Gtk.Adjustment(
            value=value,
            lower=min_val,
            upper=max_val,
            step_increment=step,
            page_increment=step * 10,
        )
        spin = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=digits)
        spin.set_value(value)
        if on_change:
            spin.connect("value-changed", on_change)
        return spin

    def _create_general_tab(self):
        """Create the general settings tab."""
        scrolled, vbox = self._create_scrolled_container()
        general = self.config.get("general", {})

        vbox.add(self._create_section_header("General Settings"))

        grid = self._create_grid()
        vbox.add(grid)

        for row, (key, value) in enumerate(general.items()):
            grid.attach(self._create_label(key), 0, row, 1, 1)

            if isinstance(value, bool):
                widget = self._create_switch(
                    value,
                    lambda sw, _, k=key: self._update_config(
                        "config.general", k, sw.get_active()
                    ),
                )
            else:
                widget = Label(label=str(value), h_align="start", h_expand=True)

            grid.attach(widget, 1, row, 1, 1)

        return scrolled

    def _build_section(
        self,
        container: Box,
        name: str,
        items: dict,
        path: str,
        *,
        control: Callable[[str, str, Any], Gtk.Widget],
        nested: Callable[[Box, str, dict, str], None],
        expander: bool = False,
        indent: bool = False,
        margin_bottom: int = 0,
    ) -> None:
        """Attach one config section - header, grid of controls, nested groups.

        The five sections this replaces differ only in presentation and in where
        they send their values, so those are the parameters:

        *control* builds the widget for a leaf value, which is also what decides
        whether a change goes to the config or to the theme. *nested* handles a
        dict value; pass the matching one of the wrappers below, so deeper
        nesting keeps the same policy.

        *expander* puts the section behind a disclosure instead of a plain
        header, *indent* shifts it right, and *margin_bottom* is the gap before
        the next section. List values are skipped - they have no generic editor.
        """
        section_path = f"{path}.{name}"
        title = name.replace("_", " ").title()

        box = Box(
            orientation="v",
            spacing=4,
            style="margin-left: 20px;" if indent else None,
        )

        grid = self._create_grid(margin_bottom=margin_bottom)
        box.add(grid)

        row = 0
        for key, value in items.items():
            if isinstance(value, dict):
                nested(box, key, value, section_path)
            elif isinstance(value, list):
                continue  # Skip lists for now
            else:
                grid.attach(self._create_label(key), 0, row, 1, 1)
                grid.attach(control(section_path, key, value), 1, row, 1, 1)
                row += 1

        if expander:
            # A disclosure owns its body; a plain header sits beside it.
            disclosure = self._create_expander(title)
            disclosure.add(box)
            container.add(disclosure)
        else:
            container.add(self._create_section_header(title))
            container.add(box)

    def _create_nested_section(
        self, container: Box, nested_name: str, nested_config: dict, path: str
    ):
        """Create an expandable section for nested config."""
        self._build_section(
            container,
            nested_name,
            nested_config,
            path,
            control=self._create_control,
            nested=self._create_nested_section,
            expander=True,
        )

    def _create_config_section(
        self, vbox: Box, section_name: str, config_items: dict, path_prefix: str
    ):
        """Create a configuration section with grid of controls."""
        self._build_section(
            vbox,
            section_name,
            config_items,
            path_prefix,
            control=self._create_control,
            nested=self._create_nested_section,
            margin_bottom=15,
        )

    def _create_modules_tab(self):
        """Create the modules settings tab."""
        scrolled, vbox = self._create_scrolled_container()
        modules = self.config.get("modules", {})

        for module_name, module_config in sorted(modules.items()):
            if isinstance(module_config, dict):
                self._create_config_section(
                    vbox, module_name, module_config, "config.modules"
                )

        return scrolled

    def _create_layout_tab(self):
        """Create the layout settings tab showing sections like left/middle/right."""
        scrolled, vbox = self._create_scrolled_container()
        layout = self.config.get("layout", {})

        vbox.add(self._create_section_header("Layout"))

        grid = self._create_grid()
        vbox.add(grid)

        for row, (section_name, items) in enumerate(layout.items()):
            grid.attach(self._create_label(section_name), 0, row, 1, 1)

            if isinstance(items, list):
                text = ", ".join([str(x) for x in items])
                entry = Entry(text=text, h_expand=False)
                entry.set_width_chars(40)

                def on_changed(e, p="config.layout", k=section_name):
                    raw = e.get_text() or ""
                    arr = [s.strip() for s in raw.split(",") if s.strip()]
                    self._update_config(p, k, arr)

                entry.connect("changed", on_changed)
                grid.attach(entry, 1, row, 1, 1)
            else:
                grid.attach(Label(label=str(items), h_align="start"), 1, row, 1, 1)

        return scrolled

    def _create_widgets_tab(self):
        """Create the widgets settings tab."""
        scrolled, vbox = self._create_scrolled_container()
        widgets = self.config.get("widgets", {})

        for widget_name, widget_cfg in sorted(widgets.items()):
            if isinstance(widget_cfg, dict):
                self._create_config_section(
                    vbox, widget_name, widget_cfg, "config.widgets"
                )

        return scrolled

    def _create_control(self, path: str, key: str, value) -> Gtk.Widget:
        """Create appropriate control for a value."""
        if isinstance(value, bool):
            return self._create_switch(
                value,
                lambda sw, _, p=path, k=key: self._update_config(p, k, sw.get_active()),
            )
        elif isinstance(value, int):
            return self._create_spinbutton(
                value,
                0,
                100,
                lambda sp, p=path, k=key: self._update_config(
                    p, k, int(sp.get_value())
                ),
            )
        elif isinstance(value, str):
            enum_options = self._get_enum_options(key)
            if enum_options:
                return self._create_combo(
                    enum_options,
                    value,
                    lambda cb, p=path, k=key: self._update_config(
                        p, k, cb.get_active_text()
                    ),
                )
            entry = Entry(text=value, h_expand=False)
            entry.set_width_chars(15)
            entry.connect(
                "changed",
                lambda e, p=path, k=key: self._update_config(p, k, e.get_text()),
            )
            return entry
        return Label(label=str(value), h_align="start")

    def _get_enum_options(self, key: str) -> list | None:
        """Get enum options for known keys."""
        enums = {
            "layer": get_literal_values(Layer),
            "anchor": get_literal_values(Anchor),
            "location": get_literal_values(Bar_Location),
            "orientation": get_literal_values(Orientation),
            "transition_type": get_literal_values(Reveal_Animations),
            "mode": get_literal_values(Widget_Mode),
            "behavior": get_literal_values(Dock_Behavior),
            "temperature_unit": get_literal_values(Temperature_Unit),
            "unit": get_literal_values(Data_Unit),
            "provider": get_literal_values(Weather_Provider),
        }
        return enums.get(key)

    def _create_theme_tab(self):
        """Create the theme settings tab."""
        scrolled, vbox = self._create_scrolled_container()

        # Main theme sections
        self._create_theme_section(
            vbox, "matugen", self.theme.get("matugen", {}), "theme"
        )
        self._create_theme_section(vbox, "font", self.theme.get("font", {}), "theme")
        self._create_theme_section(vbox, "bar", self.theme.get("bar", {}), "theme")
        self._create_theme_section(
            vbox, "modules", self.theme.get("modules", {}), "theme"
        )

        return scrolled

    def _create_theme_section(
        self, container: Box, section_name: str, section_config: dict, path: str
    ):
        """Create a top-level section for theme config (no expander)."""
        # Individual modules get their own indented section; other groups nest
        # behind expanders.
        nested = (
            self._create_theme_module_section
            if section_name == "modules"
            else self._create_theme_nested_section
        )
        self._build_section(
            container,
            section_name,
            section_config,
            path,
            control=self._create_theme_control,
            nested=nested,
            margin_bottom=15,
        )

    def _create_theme_module_section(
        self, container: Box, module_name: str, module_config: dict, path: str
    ):
        """Create a module section within the modules section (no expander)."""
        self._build_section(
            container,
            module_name,
            module_config,
            path,
            control=self._create_theme_control,
            nested=self._create_theme_nested_section,
            indent=True,
            margin_bottom=10,
        )

    def _create_theme_nested_section(
        self, container: Box, section_name: str, section_config: dict, path: str
    ):
        """Create an expandable section for theme config."""
        self._build_section(
            container,
            section_name,
            section_config,
            path,
            control=self._create_theme_control,
            nested=self._create_theme_nested_section,
            expander=True,
        )

    def _create_theme_control(self, path: str, key: str, value) -> Gtk.Widget:
        """Create appropriate control for a theme value."""
        if isinstance(value, bool):
            return self._create_switch(
                value,
                lambda sw, _, p=path, k=key: self._update_theme(p, k, sw.get_active()),
            )
        elif isinstance(value, int):
            return self._create_spinbutton(
                value,
                0,
                10000,
                lambda sp, p=path, k=key: self._update_theme(p, k, int(sp.get_value())),
            )
        elif isinstance(value, float):
            # Special handling for contrast (matugen field)
            if key == "contrast":
                return self._create_spinbutton(
                    value,
                    -1.0,
                    1.0,
                    lambda sp, p=path, k=key: self._update_theme(
                        p, k, float(sp.get_value())
                    ),
                    step=0.1,
                    digits=1,
                )
            return self._create_spinbutton(
                value,
                0.0,
                100.0,
                lambda sp, p=path, k=key: self._update_theme(
                    p, k, float(sp.get_value())
                ),
                step=0.1,
                digits=1,
            )
        elif isinstance(value, str):
            # Special handling for wallpaper field
            if key == "wallpaper":
                return self._create_wallpaper_picker(path, key, value)

            enum_options = self._get_theme_enum_options(path, key)
            if enum_options:
                return self._create_combo(
                    enum_options,
                    value,
                    lambda cb, p=path, k=key: self._update_theme(
                        p, k, cb.get_active_text()
                    ),
                )
            entry = Entry(text=value, h_expand=False)
            entry.set_width_chars(15)
            entry.connect(
                "changed",
                lambda e, p=path, k=key: self._update_theme(p, k, e.get_text()),
            )
            return entry
        return Label(label=str(value), h_align="start")

    def _create_wallpaper_picker(self, path: str, key: str, value: str) -> Gtk.Widget:
        """Create a wallpaper file picker control."""
        # Create horizontal box for entry and button
        hbox = Box(orientation="h", spacing=6)

        # Create entry for path
        entry = Entry(text=value, h_expand=True)
        entry.connect(
            "changed",
            lambda e, p=path, k=key: self._update_theme(p, k, e.get_text()),
        )
        hbox.pack_start(entry, True, True, 0)

        # Create browse button
        browse_btn = HoverButton(
            label="Browse...",
            name="settings-browse-btn",
            on_clicked=lambda _btn, e=entry, p=path, k=key: self._on_browse_wallpaper(
                _btn, e, p, k
            ),
        )

        hbox.pack_start(browse_btn, False, False, 0)

        return hbox

    def _on_browse_wallpaper(self, button, entry, path: str, key: str):
        """Handle wallpaper file selection."""
        dialog = Gtk.FileChooserDialog(
            title="Select Wallpaper",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )

        # Add filters for image files
        filter_images = Gtk.FileFilter()
        filter_images.set_name("Image files")
        filter_images.add_mime_type("image/*")
        dialog.add_filter(filter_images)

        filter_all = Gtk.FileFilter()
        filter_all.set_name("All files")
        filter_all.add_pattern("*")
        dialog.add_filter(filter_all)

        # Add buttons
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Select", Gtk.ResponseType.OK)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            if filename:
                entry.set_text(filename)
                self._update_theme(path, key, filename)

        dialog.destroy()

    def _get_theme_enum_options(self, path: str, key: str) -> list | None:
        """Get enum options for theme keys."""
        # Define all enum options
        enum_options = {
            "scheme": get_literal_values(Theme_Scheme),
            "mode": get_literal_values(Theme_Mode),
            "widget_style": get_literal_values(Widget_Style),
        }

        # Define bar style options
        bar_style_options = {
            "panel": get_literal_values(Bar_Panel_Style),
            "widget": get_literal_values(Bar_Widget_Style),
        }

        # Check for bar style options
        if path == "theme.bar.style" and key in bar_style_options:
            return bar_style_options[key]

        # Check for general enum options
        return enum_options.get(key)

    def _create_about_tab(self):
        """Create the about tab."""
        vbox = Box(orientation="v", spacing=18, style="margin: 30px;", h_align="center")

        # Logo
        logo = Image(
            image_file=f"{ASSETS_DIR}/images/logo.png",
            size=160,
            h_align="center",
            v_align="center",
        )
        vbox.add(logo)

        vbox.add(
            Label(
                label="A modular status bar for Hyprland, powered by Fabric.",
                h_align="center",
                style="margin-bottom: 12px;",
            )
        )

        repo_box = Box(orientation="h", spacing=6, h_align="center")
        repo_box.add(Label(label="GitHub:", h_align="start"))
        repo_box.add(
            Label(
                markup='<a href="https://github.com/rubiin/tsumiki">rubiin/tsumiki</a>'
            )
        )
        vbox.add(repo_box)

        return vbox

    def _update_nested_dict(self, target_dict: dict, path: str, key: str, value):
        """Update a nested dictionary at any nesting level."""
        parts = path.split(".")
        current = target_dict

        for part in parts[1:]:  # Skip the root prefix (theme/config)
            if part not in current:
                current[part] = {}
            current = current[part]

        if current.get(key) != value:
            current[key] = value
            self.modified = True
            self.save_btn.set_sensitive(True)

    def _update_theme(self, path: str, key: str, value):
        """Update theme value at any nesting level."""
        logger.info(f"[SETTINGS] Updating theme: path={path}, key={key}, value={value}")
        self._update_nested_dict(self.theme, path, key, value)

    def _update_config(self, path: str, key: str, value):
        """Update config value at any nesting level."""
        logger.info(
            f"[SETTINGS] Updating config: path={path}, key={key}, value={value}"
        )
        self._update_nested_dict(self.config, path, key, value)

    def _on_save(self, *_):
        """Save configuration."""
        try:
            write_toml_file(configuration.toml_config_file, self.config)

            # TODO: only write changed files
            write_toml_file(configuration.theme_config_file, self.theme)

            logger.info("[SETTINGS] Configuration saved successfully")
            self.modified = False
            self.save_btn.set_sensitive(False)
            send_notification("Tsumiki", "Configuration saved")
        except Exception as e:
            logger.exception(f"[SETTINGS] Failed to save configuration: {e}")
            send_notification("Tsumiki", f"Failed to save: {e}")

    def _on_reset(self, *_):
        """Reset to saved config."""
        self.config = dict(tsumiki_config)
        self.theme = dict(tsumiki_config.get("styling", {}))
        self.modified = False
        self.save_btn.set_sensitive(False)
        self._refresh_tabs()

    def _on_close(self, *_):
        """Close the window."""
        self.hide()
        SettingsGUI._visible = False

    def _on_delete(self, *_):
        """Handle window close."""
        self.hide()
        SettingsGUI._visible = False
        return True  # Prevent destruction

    def toggle(self):
        """Toggle window visibility."""
        if SettingsGUI._visible:
            self.hide()
            SettingsGUI._visible = False
        else:
            self.show_all()
            SettingsGUI._visible = True


def open_settings():
    """Open the settings GUI."""
    SettingsGUI().toggle()

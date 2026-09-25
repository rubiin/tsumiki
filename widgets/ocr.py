import time

from fabric.utils import Gdk, GLib, Gtk, exec_shell_command_async, os

from shared.widget_container import ButtonWidget
from utils.constants import ASSETS_DIR
from utils.i18n import _
from utils.widget_utils import nerd_font_icon


class OCRWidget(ButtonWidget):
    """OCR widget: left-click to grab text, right-click to pick the language."""

    def __init__(self, **kwargs):
        super().__init__(name="ocr", **kwargs)

        self.current_lang = "eng"  # default
        self.initialized = False
        self._langs_cache = None
        self._langs_cache_time = 0.0
        self._lang_lines: list[str] = []
        self._lang_finalize_id = 0

        if self.config.get("show_icon", True):
            # Create a TextIcon with the specified icon and size
            self.icon = nerd_font_icon(
                icon=self.config.get("icon"),
                props={"style_classes": ["panel-font-icon"]},
            )
            self.add_panel_content(
                self.icon,
                _("widget.ocr.label"),
                show_label=self.config.get("label", True),
            )

        # Left click for OCR
        self.connect("button-press-event", self.on_button_press)

        self.set_tooltip_if_enabled(_("widget.ocr.tooltip"))

    def lazy_init(self):
        if not self.initialized:
            self.script_file = f"{ASSETS_DIR}/scripts/ocr.sh"
            if not os.path.isfile(self.script_file):
                self.set_sensitive(False)
                self.set_tooltip_text(_("common.error"))
                return
            self.initialized = True

    def on_button_press(self, _, event):
        self.lazy_init()

        if not self.initialized:
            return  # Early exit if script not available

        base_command = f"{self.script_file} --lang {self.current_lang}"

        if self.config.get("quiet", False):
            base_command += " --no-notify"

        if event.button == 3:  # Right click
            self._show_language_menu()
        else:  # Left click
            exec_shell_command_async(base_command, lambda *_: None)

    def _show_language_menu(self):
        langs = self._get_cached_languages()
        if langs is not None:
            self._build_language_menu(langs)
            return
        self._lang_lines = []
        self._lang_finalize_id = 0
        exec_shell_command_async("tesseract --list-langs", self._on_lang_line)

    def _on_lang_line(self, line):
        self._lang_lines.append(line)
        # The async API fires once per stdout line; re-arm a short timer so the
        # menu is built ~200ms after the final line arrives.
        if self._lang_finalize_id:
            self._unregister_repeater(self._lang_finalize_id)
            GLib.source_remove(self._lang_finalize_id)
        self._lang_finalize_id = self._register_repeater(
            GLib.timeout_add(200, self._finalize_languages)
        )

    def _finalize_languages(self):
        self._lang_finalize_id = 0
        lines = self._lang_lines
        self._lang_lines = []
        if not lines:
            langs = ["eng"]
        else:
            langs = [lang.strip() for lang in lines[1:] if lang.strip()]
        self._set_cached_languages(langs)
        self._build_language_menu(langs)
        return False

    def _build_language_menu(self, langs):
        menu = Gtk.Menu(visible=True)
        menu.set_name("ocr-menu")  # For CSS targeting

        for lang in langs:
            if lang != "osd":  # Skip the OSD option
                item = Gtk.MenuItem(label=lang, visible=True)
                label = item.get_child()
                label.set_name("ocr-menu-item")  # For CSS targeting
                if lang == self.current_lang:
                    label.get_style_context().add_class("selected")
                item.connect("activate", self.on_language_selected, lang)
                menu.append(item)

        menu.popup_at_widget(self, Gdk.Gravity.SOUTH, Gdk.Gravity.NORTH, None)

    def _get_cached_languages(self):
        if self._langs_cache is not None and time.time() - self._langs_cache_time < 600:
            return self._langs_cache
        return None

    def _set_cached_languages(self, langs):
        self._langs_cache = langs
        self._langs_cache_time = time.time()

    def on_language_selected(self, _sender, lang):
        self.current_lang = lang
        self.set_tooltip_text(_("widget.ocr.lang_selected", lang=lang))

from fabric.utils import exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from utils.i18n import _

from .popup import PopupWindow


class Dialog(PopupWindow):
    """A dialog box to display a message."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        **kwargs,
    ):
        # __new__ caches the instance, so without this the second caller would
        # redo layer-shell setup and layout on a window the app already holds.
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.wrapper = Box(orientation="v", name="dialog-wrapper")

        self.title = Label(
            h_align="center",
            name="dialog-title",
        )
        self.body = Label(h_align="center", name="dialog-body")

        self.buttons = Box(
            orientation="h",
            name="dialog-buttons-box",
            v_align="center",
            h_align="center",
        )

        self._command = None
        self.ok_btn = Button(
            label=_("common.ok"),
            name="dialog-button",
            on_clicked=self._on_ok_clicked,
        )
        self.cancel_btn = Button(
            label=_("common.cancel"),
            name="dialog-button",
            on_clicked=lambda *_: self.toggle_popup(),
        )

        self.buttons.children = (self.ok_btn, self.cancel_btn)

        self.wrapper.children = (self.title, self.body, self.buttons)

        super().__init__(
            name="dialog",
            child=self.wrapper,
            transition_duration=300,
            transition_type="slide-down",
            anchor="center",
            enable_inhibitor=True,
            keyboard_mode="exclusive",
            **kwargs,
        )

    def _on_ok_clicked(self, *_):
        if self._command:
            exec_shell_command_async(self._command, lambda *_: self.toggle_popup())

    def add_content(
        self,
        title: str,
        body: str,
        command: str,
    ):
        self.title.set_label(title.upper())
        self.body.set_label(body)
        self._command = command

        return self

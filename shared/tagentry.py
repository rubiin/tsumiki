from fabric.utils import Gdk, bulk_connect
from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label

from .widget_container import BaseWidget


class TagEntry(Box, BaseWidget):
    """A widget that allows the user to enter and manage tags."""

    def __init__(self, available_tags=None, **kwargs):
        super().__init__(spacing=2, **kwargs)

        # List of available tags
        self.available_tags = available_tags or [
            "python",
            "gtk",
            "programming",
            "ui",
            "linux",
        ]

        # Track created tags
        self.tags = []

        # Create the active entry
        self.entry = Entry(**kwargs)

        bulk_connect(
            self.entry,
            {
                "key-press-event": self.on_key_press,
                "changed": self.on_text_changed,
            },
        )

        # Add entry to the box
        self.pack_start(self.entry, True, True, 0)

    def on_text_changed(self, entry):
        text = entry.get_text().strip()
        if text in self.available_tags:
            entry.get_style_context().add_class("tag-match")
        else:
            entry.get_style_context().remove_class("tag-match")

    def on_key_press(self, entry, event):
        keyval = event.keyval

        # Handle Enter key
        if keyval == Gdk.KEY_Return or keyval == Gdk.KEY_KP_Enter:
            text = entry.get_text().strip()
            if text and text in self.available_tags:
                self.create_tag(text)
                entry.set_text("")
                return True

        # Handle backspace: remove the last tag only when the entry is empty
        elif keyval == Gdk.KEY_BackSpace and entry.get_text() == "" and self.tags:
            self.remove_last_tag()
            return True

        return False

    def create_tag(self, text):
        # Create a tag button
        tag_box = EventBox(style_classes="tag")
        tag_box.connect("button-press-event", self.on_tag_clicked)
        tag_box.tag_text = text

        # Tag label - add directly without intermediate container
        label = Label(label=text, style="padding: 0 4px;")
        tag_box.add(label)

        # Insert the tag before the entry
        position = len(self.get_children()) - 1  # Position before the entry
        self.pack_start(tag_box, False, False, 0)
        self.reorder_child(tag_box, position)

        # Store the tag
        self.tags.append(tag_box)

    def remove_last_tag(self):
        if self.tags:
            last_tag = self.tags.pop()
            self.remove(last_tag)

    def on_tag_clicked(self, widget, event):
        if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            # Remove the clicked tag
            self.tags.remove(widget)
            self.remove(widget)
            self.entry.grab_focus()

    def get_tags(self):
        return [tag.tag_text for tag in self.tags]

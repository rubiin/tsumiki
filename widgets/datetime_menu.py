import contextlib

from fabric.notifications import Notification
from fabric.utils import Gtk, bulk_connect, logger, math
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.datetime import DateTime
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.separator import Separator

import utils.constants as constants
import utils.functions as helpers
from services import notification_service
from shared.buttons import HoverButton
from shared.circle_image import CircularImage
from shared.list import ListBox
from shared.mixins import PopoverMixin
from shared.notification_card import (
    app_icon,
    close_button,
    header,
    summary_label,
    timestamp_label,
)
from shared.widget_container import ButtonWidget
from utils.i18n import _
from utils.icons import get_text_icon
from utils.widget_utils import (
    get_notification_image_pixbuf,
    nerd_font_icon,
)
from widgets.extended_datetime import ExtendedDateTime


class DateMenuNotification(Box):
    """A widget to display a notification."""

    def __init__(
        self,
        id: int,
        notification: Notification,
        on_close=None,
        **kwargs,
    ):
        super().__init__(
            size=(constants.NOTIFICATION_WIDTH, -1),
            name="datemenu-notification-box",
            h_expand=True,
            spacing=4,
            orientation="v",
            **kwargs,
        )

        self._notification = notification
        self._id = id

        title = self._notification.summary or notification.app_name

        # A grouped row clears the whole deck instead of a single entry.
        style_classes = ["close-button"]
        tooltip_text = None
        if on_close is not None:
            style_classes.append("group-clear-button")
            tooltip_text = _("widget.date_time.clear_group")

        self.close_button = close_button(
            on_close or self.remove_notification,
            tooltip_text=tooltip_text,
            style_classes=style_classes,
        )

        header_row = header(
            leading=[
                app_icon(notification),
                summary_label(
                    helpers.parse_markup(str(title)),
                    name="date-menu-notification-summary",
                ),
            ],
            trailing=[
                timestamp_label(self._format_time()),
                self.close_button,
            ],
            spacing=4,
        )

        body_label = Label(
            markup=helpers.parse_markup(self._notification.body or ""),
            v_align="start",
            h_align="start",
            name="date-menu-notification-body",
            line_wrap="word-char",
            ellipsization="end",
            chars_width=20,
            max_chars_width=45,
            style_classes="body",
        )
        # Cap the body at two lines so long notifications don't blow up the row.
        body_label.set_lines(2)

        image_widget = self._notification_image_widget()
        body_children = [body_label]
        if image_widget is not None:
            body_children.insert(0, image_widget)

        self.children = (
            header_row,
            Box(
                spacing=8,
                orientation="h",
                style_classes="notification-body",
                v_align="start",
                h_align="start",
                children=tuple(body_children),
            ),
        )

    def _notification_image_widget(self):
        """The notification's own artwork, reusing the service pixbuf cache."""
        image_size = math.ceil(0.75 * constants.NOTIFICATION_IMAGE_SIZE)

        image_pixbuf = notification_service.get_cached_pixbuf(self._id, image_size)
        if image_pixbuf is None:
            image_pixbuf = get_notification_image_pixbuf(
                self._notification, image_size
            )
            if image_pixbuf is None:
                return None
            notification_service.cache_pixbuf(self._id, image_pixbuf, image_size)

        return CircularImage(pixbuf=image_pixbuf, size=image_size)

    def _format_time(self) -> str:
        return helpers.format_relative_timestamp(
            getattr(self._notification, "time", None)
        )

    def remove_notification(self, *_):
        notification_service.remove_notification(self._id)
        # The notification_count handler may already have reloaded the list,
        # destroying this row - only destroy if it is still in the tree.
        if self.get_parent() is not None:
            self.destroy()


class DateNotificationMenu(Box):
    """A menu to display the date and time information."""

    NUM_STACKED_NOTIFICATIONS = 3

    def __init__(
        self,
        config: dict,
        **kwargs,
    ):
        super().__init__(
            name="date_time-menu",
            orientation="h",
            **kwargs,
        )

        self.config = config
        self.pixel_size = 13
        self.notification_enabled = config.get("notification", {}).get("enabled", True)
        # Grouping toggle lives in this widget's notification sub-config.
        self.grouping_enabled = config.get("notification", {}).get(
            "notification_grouping", True
        )
        self._vadj_handler = None

        if self.notification_enabled:
            self.all_notifications: list[Notification] = (
                notification_service.get_deserialized()
            )

            self.notifications_listbox = ListBox(
                name="notification-list",
                h_align="center",
                h_expand=True,
                visible=len(self.all_notifications) > 0,
            )

            self.loaded_count = 0
            self.loading = False
            self.batch_size = 8  # how many to load per scroll
            self.grouped_entries: list[tuple[str, list[Notification]]] = []
            self._app_expand_state: dict[str, bool] = {}
            self._rebuild_grouped_entries()
            self._load_next_batch()

            # Placeholder for when there are no notifications
            self.placeholder = Box(
                style_classes="placeholder",
                orientation="v",
                h_align="center",
                v_align="center",
                v_expand=True,
                h_expand=True,
                visible=len(self.all_notifications) == 0,
                children=(
                    nerd_font_icon(
                        icon=get_text_icon("notifications.checked", "󱇥"),
                        props={
                            "style_classes": ["panel-font-icon", "placeholder-icon"],
                        },
                    ),
                    Label(
                        label=_("widget.date_time.all_caught_up"),
                        style_classes="placeholder-text",
                    ),
                ),
            )

            self.dnd_switch = Gtk.Switch(
                name="notification-switch",
                active=False,
                valign=Gtk.Align.CENTER,
                visible=True,
            )

            notification_column_header = Box(
                style_classes="header",
                orientation="h",
                children=(
                    Label(label=_("widget.date_time.dnd"), name="dnd-text"),
                    self.dnd_switch,
                ),
            )

            self.clear_icon = nerd_font_icon(
                name="clear-icon",
                icon=get_text_icon("trash.empty", "")
                if len(self.all_notifications) == 0
                else get_text_icon("trash.full", ""),
                props={"style_classes": ["panel-font-icon"]},
            )

            self.clear_button = HoverButton(
                name="clear-button",
                v_align="center",
                child=self.clear_icon,
                on_clicked=self._handle_clear_click,
            )
            notification_column_header.pack_end(
                self.clear_button,
                False,
                False,
                0,
            )

            self.scrolled_window = ScrolledWindow(
                v_expand=True,
                style_classes="notification-scrollable",
                v_scrollbar_policy="automatic",
                h_scrollbar_policy="never",
                child=Box(children=(self.placeholder, self.notifications_listbox)),
            )

            vadj = self.scrolled_window.get_vadjustment()
            self._vadj_handler = vadj.connect("value-changed", self.on_scroll)
            self.connect("destroy", self._on_destroy)

            notification_column = Box(
                name="notification-column",
                orientation="v",
                children=(
                    notification_column_header,
                    self.scrolled_window,
                ),
            )
            self.add(notification_column)
            self.add(Separator())

        if config.get("calendar", True):
            date_column = Box(
                style_classes="date-column",
                orientation="v",
                children=(
                    DateTime(
                        "%H:%M"
                        if self.config.get("clock_format", "24h") == "24h"
                        else "%I:%M",
                        name="clock",
                    ),
                    Box(
                        style_classes="calendar",
                        v_expand=True,
                        children=(
                            Gtk.Calendar(
                                visible=True,
                                hexpand=True,
                                halign=Gtk.Align.CENTER,
                            )
                        ),
                    ),
                ),
            )

            self.add(date_column)

        if self.notification_enabled:
            bulk_connect(
                notification_service,
                {
                    "notification-added": self.on_new_notification,
                    "notification-closed": self.on_notification_closed,
                    "notification_count": self.on_notification_count,
                    "clear_all": self.on_clear_all_notifications,
                    "dnd": self.on_dnd_switch,
                },
            )

            self.dnd_switch.connect("notify::active", self.on_dnd_switch_toggled)

    def _handle_clear_click(self, *_):
        """Handle clear button click."""

        self.notifications_listbox.remove_all()
        self.all_notifications.clear()
        self.grouped_entries.clear()
        self.loaded_count = 0

        notification_service.clear_all_notifications()
        self.clear_icon.set_label(get_text_icon("trash.empty", ""))

    def _notification_id(self, notification: Notification) -> int | None:
        """Get notification ID for both serialized and deserialized objects."""
        if hasattr(notification, "__getitem__"):
            try:
                return int(notification["id"])
            except Exception as e:
                logger.debug(f"[DateTime] Failed to get notification ID: {e}")
                pass

        notif_id = getattr(notification, "id", None)
        if notif_id is None:
            return None

        try:
            return int(notif_id)
        except (TypeError, ValueError):
            return None

    def _notification_app_name(self, notification: Notification) -> str:
        """Resolve a stable app name used for grouping."""
        app_name = getattr(notification, "app_name", None)
        if not app_name and hasattr(notification, "__getitem__"):
            try:
                app_name = notification["app_name"]
            except Exception as e:
                logger.debug(f"[DateTime] Failed to get app_name: {e}")
                app_name = None

        return str(app_name or "Unknown")

    def _notification_urgency(self, notification: Notification) -> int:
        """Get urgency (0=low, 1=normal, 2=critical) for both serialized
        and deserialized objects."""
        urgency = getattr(notification, "urgency", None)
        if urgency is None and hasattr(notification, "__getitem__"):
            try:
                urgency = notification["urgency"]
            except Exception:
                urgency = None
        try:
            return int(urgency) if urgency is not None else 1
        except (TypeError, ValueError):
            return 1

    def _rebuild_grouped_entries(self):
        """Build app-wise deck entries."""
        if not self.grouping_enabled:
            # Flat list (grouping disabled): one entry per notification,
            # newest first.
            ordered = sorted(
                self.all_notifications,
                key=lambda n: self._notification_id(n) or 0,
                reverse=True,
            )
            self._app_expand_state.clear()
            self.grouped_entries = [
                (self._notification_app_name(n), [n]) for n in ordered
            ]
            return

        grouped: dict[str, list[Notification]] = {}

        for notification in self.all_notifications:
            app_name = self._notification_app_name(notification)
            if app_name not in grouped:
                grouped[app_name] = []
            grouped[app_name].append(notification)

        # Keep newest notification at top in each app deck.
        for app_name in grouped:
            grouped[app_name].sort(
                key=lambda n: self._notification_id(n) or 0,
                reverse=True,
            )

        # Order app decks by urgency first (any critical member), then by
        # latest notification (matches SwayNC's list_box_sort_func).
        app_order = sorted(
            grouped,
            key=lambda app: (
                0
                if any(self._notification_urgency(n) == 2 for n in grouped[app])
                else 1,
                -(self._notification_id(grouped[app][0]) or 0),
            ),
        )

        entries: list[tuple[str, list[Notification]]] = []
        for app_name in app_order:
            entries.append((app_name, grouped[app_name]))
            self._app_expand_state.setdefault(app_name, False)

        removed_apps = set(self._app_expand_state) - set(app_order)
        for app_name in removed_apps:
            self._app_expand_state.pop(app_name, None)

        self.grouped_entries = entries

    def _reload_grouped_list(self):
        """Refresh the listbox from grouped entries."""
        self.notifications_listbox.remove_all()
        self.loaded_count = 0
        self._rebuild_grouped_entries()
        self._load_next_batch()

        has_notifications = len(self.all_notifications) > 0
        self.placeholder.set_visible(not has_notifications)
        self.notifications_listbox.set_visible(has_notifications)
        self.clear_icon.set_label(
            get_text_icon("trash.full", "")
            if has_notifications
            else get_text_icon("trash.empty", "")
        )

    def _bake_group_deck(
        self,
        app_name: str,
        notifications: list[Notification],
    ) -> Gtk.ListBoxRow:
        """Create one collapsible deck row for a single app group."""
        if len(notifications) == 1:
            single_notification = DateMenuNotification(
                notification=notifications[0],
                id=self._notification_id(notifications[0]) or 0,
            )
            return Gtk.ListBoxRow(
                visible=True,
                selectable=False,
                activatable=False,
                name="notification-group-row",
                child=single_notification,
            )

        expanded = self._app_expand_state.get(app_name, False)

        def _toggle_group(*_):
            is_expanded = not self._app_expand_state.get(app_name, False)
            self._app_expand_state[app_name] = is_expanded
            revealer.set_reveal_child(is_expanded)
            peek_box.set_visible(not is_expanded and len(notifications) > 1)
            group_header.set_visible(is_expanded)
            if is_expanded:
                deck.add_style_class("group-expanded")
            else:
                deck.remove_style_class("group-expanded")

        def _close_group(*_):
            ids = {self._notification_id(n) for n in notifications}
            ids.discard(None)
            for nid in ids:
                # Each removal emits notification_count, which triggers the
                # on_notification_count handler to re-sync and reload the list.
                notification_service.remove_notification(nid)

        # Unified expanded group header: icon + name + collapse + close-all
        collapse_button = Button(
            name="notification-group-collapse-button",
            v_align="center",
            child=nerd_font_icon(
                icon=get_text_icon("ui.fold", ""),
                props={"style_classes": ["panel-font-icon"]},
            ),
            on_clicked=_toggle_group,
        )

        # Shares the shared builder; the name keeps the group-deck styling.
        close_all_button = close_button(
            _close_group,
            name="notification-group-close-all-button",
        )

        count = len(notifications)

        count_label = Label(
            label=str(count),
            style_classes="notification-group-count",
        )

        # Every row carries its own app icon, so the deck header only labels
        # the group.
        group_header = header(
            leading=[
                Label(
                    label=app_name,
                    h_expand=True,
                    h_align="start",
                    style_classes="notification-group-title",
                ),
            ],
            trailing=[
                count_label,
                collapse_button,
                close_all_button,
            ],
            spacing=6,
            style_classes="notification-group-header",
            name="notification-group-header",
            h_expand=True,
            visible=expanded,
        )

        top_notification = DateMenuNotification(
            notification=notifications[0],
            id=self._notification_id(notifications[0]) or 0,
            style_classes="notification-group-top",
            on_close=_close_group,
        )

        peek_layer_count = max(
            0,
            min(self.NUM_STACKED_NOTIFICATIONS, count) - 1,
        )
        peek_layers = tuple(
            Box(
                style_classes=[
                    "notification-group-peek-layer",
                    f"notification-group-peek-layer-depth-{index + 1}",
                ],
            )
            for index in range(peek_layer_count)
        )

        peek_box = Box(
            name="notification-group-peek",
            orientation="v",
            spacing=3,
            visible=(not expanded and count > 1),
            children=peek_layers,
        )

        collapsed_stack = Box(
            name="notification-group-collapsed-stack",
            orientation="v",
            spacing=0,
            children=(top_notification, peek_box),
        )

        items_box = Box(
            name="notification-group-items",
            orientation="v",
            spacing=8,
            children=tuple(
                DateMenuNotification(
                    notification=notification,
                    id=self._notification_id(notification) or 0,
                )
                for notification in notifications[1:]
            ),
        )

        revealer = Revealer(
            child=items_box,
            reveal_child=expanded,
            transition_type="slide_down",
            transition_duration=600,
        )

        deck = Box(
            name="notification-group-deck",
            orientation="v",
            spacing=0,
            children=(group_header, collapsed_stack, revealer),
        )

        if expanded:
            deck.add_style_class("group-expanded")

        click_surface = EventBox()
        click_surface.add(deck)

        row = Gtk.ListBoxRow(
            visible=True,
            selectable=False,
            activatable=False,
            name="notification-group-row",
            child=click_surface,
        )

        def _on_group_press(*_):
            if not self._app_expand_state.get(app_name, False):
                _toggle_group()

        click_surface.connect("button-press-event", _on_group_press)

        return row

    def _load_next_batch(self):
        """Load the next batch of notifications into the listbox."""
        if self.loading or self.loaded_count >= len(self.grouped_entries):
            return

        self.loading = True

        items_to_add = min(
            self.batch_size,
            len(self.grouped_entries) - self.loaded_count,
        )
        for i in range(self.loaded_count, self.loaded_count + items_to_add):
            app_name, notifications = self.grouped_entries[i]
            self.notifications_listbox.add(
                self._bake_group_deck(app_name, notifications)
            )

        self.loaded_count += items_to_add
        self.loading = False

    def _on_destroy(self, *_):
        if self._vadj_handler is not None and self.scrolled_window is not None:
            with contextlib.suppress(Exception):
                self.scrolled_window.get_vadjustment().disconnect(self._vadj_handler)
            self._vadj_handler = None

    def on_scroll(self, adjustment: Gtk.Adjustment):
        """Load more notifications when user scrolls near the bottom."""
        value = adjustment.get_value()
        upper = adjustment.get_upper()
        page_size = adjustment.get_page_size()

        if value + page_size >= upper - 50:
            self._load_next_batch()

    def on_dnd_switch_toggled(self, switch: Gtk.Switch, state):
        notification_service.dont_disturb = switch.get_active()

    def on_dnd_switch(self, _, value, *args):
        self.dnd_switch.set_active(value)

    def on_clear_all_notifications(self, *_):
        """Handle clearing all notifications."""
        self.all_notifications.clear()
        self.grouped_entries.clear()
        self._app_expand_state.clear()
        self.loaded_count = 0
        self.clear_icon.set_label(get_text_icon("trash.empty", ""))
        self.placeholder.set_visible(True)
        self.notifications_listbox.set_visible(False)
        self.notifications_listbox.remove_all()

    def on_notification_count(self, *_):
        """Re-sync notifications from the service when the count changes."""
        if getattr(self, "_syncing_notification_count", False):
            return
        if notification_service.count == len(self.all_notifications):
            return

        self._syncing_notification_count = True
        try:
            self.all_notifications = notification_service.get_deserialized()
            self._reload_grouped_list()
        finally:
            self._syncing_notification_count = False

    def on_notification_closed(self, _, id, reason):
        """Handle notification being closed."""
        if reason not in {"dismissed-by-user", "dismissed-by-limit"}:
            return

        self.all_notifications = [
            n for n in self.all_notifications if self._notification_id(n) != id
        ]
        self._reload_grouped_list()

    def on_new_notification(self, fabric_notification, id):
        if notification_service.dont_disturb:
            return

        fabric_notification: Notification = (
            fabric_notification.get_notification_from_id(id)
        )

        # A replacement supersedes the entry it targets - drop the stale one
        # so in-place updates don't stack up duplicates in the menu.
        replaces_id = getattr(fabric_notification, "replaces_id", 0) or 0
        if replaces_id:
            self.all_notifications = [
                n
                for n in self.all_notifications
                if self._notification_id(n) != replaces_id
            ]

        # The notification_count handler may already have synced this
        # notification in from the service - avoid inserting it twice.
        if any(self._notification_id(n) == id for n in self.all_notifications):
            return

        self.all_notifications.insert(0, fabric_notification)
        self._reload_grouped_list()


class DateTimeWidget(ButtonWidget, PopoverMixin):
    """A widget to display the date and time."""

    def __init__(self, **kwargs):
        super().__init__(name="date_time", **kwargs)

        notification_config = self.config.get("notification", {})

        clock_format = "%I:%M"
        if self.config.get("clock_format", "24h") == "24h":
            clock_format = "%H:%M"
        date_format = f"{self.config.get('date_format', '%b %d')} {clock_format}"

        if notification_config.get("enabled", True):
            self.notification_indicator = nerd_font_icon(
                icon=get_text_icon("notifications.noisy", "󰂜"),
                name="notification-indicator",
                props={
                    "style_classes": ["panel-font-icon"],
                    "visible": True,
                },
            )

            self.count_label = Label(
                name="notification-count",
                label=str(notification_service.count),
                v_align="start",
                visible=notification_config.get("count", True),
            )

            if (
                notification_config.get("hide_count_on_zero", False)
                and notification_service.count == 0
            ):
                self.notification_indicator.set_style_classes(
                    ["panel-font-icon", "no-notifications"]
                )
                self.count_label.set_visible(False)

            bulk_connect(
                notification_service,
                {
                    "notification_count": self.on_notification_count,
                    "dnd": self.on_dnd_switch,
                },
            )

            self.container_box.add(self.notification_indicator)
            self.container_box.add(self.count_label)

        is_nepali_time = self.config.get("nepali_date", False)

        date_label = ExtendedDateTime(
            formatters=date_format,
            nepali_time=is_nepali_time,
        )

        if self.config.get("hover_reveal", True):
            self.revealer = Revealer(
                child=date_label,
                transition_duration=self.config.get("reveal_duration", 500),
                transition_type="slide_right",
            )
            self.container_box.add(self.revealer)
        else:
            self.container_box.add(date_label)

        self.setup_popover(lambda: DateNotificationMenu(config=self.config))

    def on_notification_count(self, _, value, *args):
        if value > 0:
            self.count_label.set_text(str(value))
            self.notification_indicator.set_style_classes(["panel-font-icon"])
            self.count_label.set_visible(True)
        elif self.config.get("notification", {}).get("hide_count_on_zero", False):
            self.notification_indicator.set_style_classes(
                ["panel-font-icon", "no-notifications"]
            )
            self.count_label.set_visible(False)

    def on_dnd_switch(self, _, value, *args):
        if value:
            self.notification_indicator.set_label(
                get_text_icon("notifications.silent", "󰪑"),
            )

        else:
            self.notification_indicator.set_label(
                get_text_icon("notifications.noisy", "󰂜"),
            )

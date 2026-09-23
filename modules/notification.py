import os
from typing import ClassVar

from fabric.notifications import (
    Notification,
    NotificationAction,
    Notifications,
)
from fabric.utils import (
    Gdk,
    GdkPixbuf,
    GLib,
    Gtk,
    bulk_connect,
    logger,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.grid import Grid
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.widget import Widget

import utils.constants as constants
import utils.functions as helpers
from services import notification_service
from shared.buttons import HoverButton
from shared.circle_image import CircularImage
from shared.widget_container import BaseWindow
from utils.colors import Colors
from utils.icon_resolver import IconResolver
from utils.icons import get_text_icon
from utils.widget_settings import BarConfig
from utils.widget_utils import get_notification_image_pixbuf, nerd_font_icon

# Swipe threshold for dismissing notifications (normalized: 0.0 to 1.0)
_SWIPE_DISMISS_THRESHOLD = 0.35
BAR_COLOR = (1.0, 0.36, 0.36)  # RGB for the progress bar color


class NotificationPopup(BaseWindow):
    """A widget to grab and display notifications."""

    def __init__(self, widget_config: BarConfig, **kwargs):
        self._server = notification_service
        self._active_notifications: dict[int, NotificationRevealer] = {}

        self.widget_config = widget_config

        self.config = widget_config.get("modules", {}).get("notification", {})

        self.ignored_apps = helpers.unique_list(self.config.get("ignored", []))

        self.persist = self.config.get("persist", {})

        if self.config.get("play_sound", False):
            self.sound_file = f"{constants.ASSETS_DIR}/sounds/{self.config.get('sound_file', 'notification4')}.mp3"  # noqa: E501

        self.notifications = Box(
            v_expand=True,
            h_expand=True,
            style="margin: 1px 0 1px 1px;",
            orientation="v",
            spacing=5,
        )
        self._server.connect("notification-added", self.on_new_notification)

        super().__init__(
            anchor=self.config.get("anchor", "center"),
            layer="overlay",
            all_visible=True,
            visible=True,
            exclusive=False,
            title="tsumiki-notifications",
            child=self.notifications,
            **kwargs,
        )

    def _unregister_notification(
        self,
        notification_id: int,
        revealer: "NotificationRevealer",
    ):
        if self._active_notifications.get(notification_id) is revealer:
            self._active_notifications.pop(notification_id, None)

    def on_new_notification(self, fabric_notification: Notifications, id):
        notification = fabric_notification.get_notification_from_id(id)

        replaces_id = getattr(notification, "replaces_id", 0) or 0

        # Check if the notification is in the "do not disturb" mode, hacky way.
        # A hidden replacement still removes the old notification (SwayNC
        # parity): DND/ignored notifications never reach the popup, but a
        # stale visible revealer for the replaced one must not linger.
        if self._server.dont_disturb or notification.app_name in self.ignored_apps:
            if replaces_id:
                self._server.drop_registry_entry(replaces_id)
                old_box = self._active_notifications.pop(replaces_id, None)
                if old_box is not None:
                    old_box.notification_box.stop_timeout()
                    old_box.destroy()
            return

        if replaces_id:
            # Drop the replaced notification from the server's in-memory
            # registry so its Notification object doesn't leak there.
            self._server.drop_registry_entry(replaces_id)

            old_box = self._active_notifications.pop(replaces_id, None)
            if old_box is not None:
                old_box.replace_notification(notification)
                # Disconnect the old destroy handler (wired to replaces_id)
                # and re-register with the new id so cleanup targets the
                # correct key when the box eventually self-destroys.
                if hasattr(old_box, "_destroy_handler_id"):
                    old_box.disconnect(old_box._destroy_handler_id)
                old_box._destroy_handler_id = old_box.connect(
                    "destroy",
                    lambda *_: self._unregister_notification(id, old_box),
                )
                self._active_notifications[id] = old_box
                return

        new_box = NotificationRevealer(self.config, notification)
        self.notifications.add(new_box)
        new_box.set_reveal_child(True)
        self._active_notifications[id] = new_box
        new_box._destroy_handler_id = new_box.connect(
            "destroy", lambda *_: self._unregister_notification(id, new_box)
        )

        logger.info(
            f"{Colors.INFO}[Notification] New notification from "
            f"{Colors.OKGREEN}{notification.app_name}"
        )

        if self.persist.get("enabled", True):
            if notification.urgency == 0 and not self.persist.get("low", True):
                return
            if notification.urgency == 1 and not self.persist.get("normal", True):
                return
            if notification.urgency == 2 and not self.persist.get("critical", True):
                return

            self._server.cache_notification(
                self.widget_config, notification, self.persist.get("max_count", 100)
            )

        if self.config.get("play_sound", False):
            helpers.play_sound(self.sound_file)


class NotificationWidget(EventBox):
    """A widget to display a notification with swipe-to-dismiss support."""

    def __init__(
        self,
        config: dict,
        notification: Notification,
        **kwargs,
    ):
        super().__init__(
            size=(constants.NOTIFICATION_WIDTH, -1),
            name="notification-eventbox",
            **kwargs,
        )

        self.config = config
        self._notification = notification
        self._timeout_id = None
        self._time_remaining = 0
        self._last_tick_time = 0

        # Swipe gesture state
        self._drag_start_x: float | None = None
        self._drag_start_y: float | None = None
        self._is_dragging = False
        self._swipe_offset = 0.0

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )

        self.progress_timeout = Gtk.DrawingArea(
            visible=True,
            name="notification-progress-timeout",
        )
        self.progress_timeout.set_size_request(-1, 2)
        self.progress_timeout.connect("draw", self._draw_progress)

        self.notification_box = Box(
            name="notification",
            orientation="v",
        )

        if notification.urgency == 2:
            self.notification_box.add_style_class("critical")

        self._wire_events()

        # Strip inline <img src=...> tags from the body; the first source is
        # rendered as an image when the notification has no image hint.
        body_text, body_image_src = helpers.extract_body_image(
            self._notification.body or ""
        )
        max_collapsed_lines = self.config.get("max_lines", 4)
        max_expanded_lines = self.config.get("max_expanded_lines", 20)
        is_long_content = (
            body_text.count("\n") + 1 > max_collapsed_lines or len(body_text) > 150
        )

        header = self._build_header(
            notification, is_long_content, max_collapsed_lines, max_expanded_lines
        )
        body = self._build_body(
            notification,
            body_text,
            body_image_src,
            is_long_content,
            max_collapsed_lines,
            max_expanded_lines,
        )
        self.actions_container_grid = self._build_actions(notification, body_text)

        self.notification_box.children = (
            self.progress_timeout,
            header,
            body,
            self.actions_container_grid,
        )
        self.add(self.notification_box)

        self._notification.connect("closed", lambda *_: self.stop_timeout())

    def _wire_events(self):
        """Connect all input event handlers."""
        bulk_connect(
            self,
            {
                "button-press-event": self.on_button_press,
                "button-release-event": self._on_button_release,
                "motion-notify-event": self._on_motion_notify,
                "enter-notify-event": self.on_hover,
                "leave-notify-event": self.on_unhover,
            },
        )

    def _draw_progress(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()

        elapsed = self.get_timeout() - self._time_remaining
        frac = (
            max(0.0, 1.0 - (elapsed / self.get_timeout()))
            if self.get_timeout()
            else 1.0
        )

        bar_width = width * frac
        x = (width - bar_width) / 2  # shrinks inward from both edges toward center

        r, g, b = BAR_COLOR
        cr.set_source_rgb(r, g, b)
        cr.rectangle(x, 0, bar_width, height)
        cr.fill()
        return False

    def _build_header(
        self,
        notification: Notification,
        is_long_content: bool,
        max_collapsed_lines: int,
        max_expanded_lines: int,
    ) -> Box:
        """Build notification header: icon, summary, optional expand, close."""
        header_container = Box(
            spacing=8, orientation="h", style_classes="notification-header"
        )

        header_container.children = (
            Image(
                pixbuf=IconResolver().resolve_icon(
                    None, notification.app_name, 25
                ),
                size=25,
            ),
            Label(
                markup=helpers.parse_markup(
                    self._notification.summary
                    if self._notification.summary
                    else notification.app_name,
                ),
                h_align="start",
                style_classes="summary",
                max_chars_width=30,
                line_wrap="word-char",
            ),
        )

        self.expand_button = None
        if is_long_content:
            self._is_expanded = False
            self.expand_button = Button(
                style_classes="expand-button",
                child=nerd_font_icon(
                    icon=get_text_icon("chevron.down", ""),
                    props={"style_classes": ["panel-font-icon", "expand-icon"]},
                ),
                on_clicked=lambda *_: self._toggle_expand(
                    max_collapsed_lines, max_expanded_lines
                ),
            )

        close_btn = Button(
            v_align="center",
            h_align="center",
            style_classes="close-button",
            tooltip_text="Dismiss notification",
            child=nerd_font_icon(
                icon=get_text_icon("ui.window_close", ""),
                props={"style_classes": ["panel-font-icon", "close-icon"]},
            ),
            on_clicked=self.on_close_button_clicked,
        )

        header_container.pack_end(close_btn, False, False, 0)
        if self.expand_button:
            header_container.pack_end(self.expand_button, False, False, 0)

        if self.config.get("show_timestamp", True):
            header_container.pack_end(
                Label(
                    label=helpers.format_relative_timestamp(self._notification.time),
                    v_align="center",
                    style_classes="timestamp",
                ),
                False,
                False,
                0,
            )

        return header_container

    def _build_body(
        self,
        notification: Notification,
        body_text: str,
        body_image_src: str | None,
        is_long_content: bool,
        max_collapsed_lines: int,
        max_expanded_lines: int,
    ) -> Box:
        """Build notification body: optional image and expandable text label."""
        body_container = Box(
            spacing=4,
            orientation="h",
            style_classes="notification-body",
            v_align="start",
            h_align="start",
        )

        image_pixbuf = get_notification_image_pixbuf(self._notification)
        if image_pixbuf is None and body_image_src:
            image_pixbuf = self._load_body_image_pixbuf(body_image_src)

        if image_pixbuf is not None:
            body_container.add(
                CircularImage(
                    pixbuf=image_pixbuf,
                    h_expand=True,
                    v_expand=True,
                    size=constants.NOTIFICATION_IMAGE_SIZE,
                ),
            )

        if is_long_content:
            self.body_label = Label(
                markup=helpers.parse_markup(body_text),
                v_align="start",
                h_align="start",
                style_classes="body",
                line_wrap="word-char",
                max_chars_width=38,
            )
            self.body_label.set_lines(max_collapsed_lines)
            self.body_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            body_container.add(self.body_label)
        else:
            body_container.add(
                Label(
                    markup=helpers.parse_markup(body_text),
                    v_align="start",
                    h_align="start",
                    style_classes="body",
                    line_wrap="word-char",
                    max_chars_width=38,
                ),
            )

        return body_container

    def _load_body_image_pixbuf(self, src: str) -> GdkPixbuf.Pixbuf | None:
        """Resolve an inline ``<img src=...>`` body image to a pixbuf or None."""
        path = helpers.expand_env(src)
        if path.startswith("file://"):
            path = path[len("file://") :]
        if not path or not os.path.exists(path):
            return None
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_size(
                path,
                constants.NOTIFICATION_IMAGE_SIZE,
                constants.NOTIFICATION_IMAGE_SIZE,
            )
        except Exception:
            logger.exception(f"[Notification] Failed to load body image: {src}")
            return None

    def _build_actions(self, notification: Notification, body_text: str) -> Grid:
        """Build the actions grid from notification actions.

        When the body contains a one-time (2FA) code, a COPY button is
        prepended that copies the code and dismisses the notification.
        """
        max_actions = self.config.get("max_actions", 3)
        actions = notification.actions[:max_actions]

        copy_code = None
        if self.config.get("copy_code_action", True):
            copy_code = helpers.extract_one_time_code(body_text)

        copy_offset = 1 if copy_code else 0
        total_actions = len(actions) + copy_offset
        buttons: list[Button] = [
            ActionButton(action, i + copy_offset, total_actions)
            for i, action in enumerate(actions)
        ]
        if copy_code:
            buttons.insert(0, CopyCodeButton(copy_code, 0, total_actions, notification))

        grid = Grid(
            orientation="h",
            name="notification-action-box",
            h_expand=True,
            row_homogeneous=True,
            column_spacing=4,
        )
        grid.attach_flow(buttons, max_actions)
        return grid

    def _toggle_expand(self, collapsed_lines: int, expanded_lines: int):
        """Toggle between collapsed and expanded body text."""
        self._is_expanded = not self._is_expanded
        if self._is_expanded:
            self.body_label.set_lines(expanded_lines)
            self.expand_button.get_child().set_label(get_text_icon("chevron.up", ""))
        else:
            self.body_label.set_lines(collapsed_lines)
            self.expand_button.get_child().set_label(get_text_icon("chevron.down", ""))

    def on_close_button_clicked(self, *_):
        self._notification.close("dismissed-by-user")
        self.stop_timeout()

    def start_timeout(self):
        self.stop_timeout()
        self._time_remaining = self.get_timeout()
        self._last_tick_time = GLib.get_monotonic_time()
        self._timeout_id = self.progress_timeout.add_tick_callback(self._tick_callback)

    def _tick_callback(self, widget, frame_clock) -> bool:
        """Called on every frame (vsync). Updates progress bar smoothly."""
        now = GLib.get_monotonic_time()
        elapsed_ms = (now - self._last_tick_time) / 1000
        self._last_tick_time = now
        self._time_remaining = max(0, self._time_remaining - elapsed_ms)

        self.progress_timeout.queue_draw()

        if self._time_remaining <= 0:
            self.close_notification()
            return False  # Stop ticking

        return True  # Keep ticking on next frame

    def stop_timeout(self):
        if self._timeout_id is not None:
            self.progress_timeout.remove_tick_callback(self._timeout_id)
            self._timeout_id = None

    def close_notification(self):
        self._notification.close("expired")
        self.stop_timeout()
        return False

    def on_button_press(self, widget, event):
        """Handle button press - start drag tracking for swipe gestures."""
        if event.button == 1:
            # Left click: start tracking for potential swipe
            self._drag_start_x = event.x
            self._drag_start_y = event.y
            self._is_dragging = False
            self._swipe_offset = 0.0
            return True
        else:
            # Right/middle click: dismiss immediately
            self._notification.close("dismissed-by-user")
            self.stop_timeout()
            return True

    def _render_swipe_progress(self, dx: float, widget_width: int):
        """Update swipe offset state and apply visual translation + fade."""
        self._swipe_offset = dx / widget_width
        self.notification_box.set_margin_start(int(dx) if dx > 0 else 0)
        self.notification_box.set_margin_end(int(-dx) if dx < 0 else 0)
        opacity = max(0.3, 1.0 - abs(self._swipe_offset))
        self.notification_box.set_opacity(opacity)

    def _on_motion_notify(self, widget, event):
        """Handle mouse motion for swipe gesture."""
        if self._drag_start_x is None:
            return False

        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y

        if abs(dx) > 10 and abs(dx) > abs(dy):
            self._is_dragging = True
            self.pause_timeout()
            alloc = widget.get_allocation()
            if alloc.width > 0:
                self._render_swipe_progress(dx, alloc.width)

        return True

    def _on_button_release(self, widget, event):
        """Handle button release - complete swipe gesture if threshold met."""
        if self._drag_start_x is None:
            return False

        if self._is_dragging:
            if abs(self._swipe_offset) >= _SWIPE_DISMISS_THRESHOLD:
                self._notification.close("dismissed-by-user")
            else:
                self._reset_swipe_position()

        # Reset drag state
        self._drag_start_x = None
        self._drag_start_y = None
        self._is_dragging = False
        self._swipe_offset = 0.0

        return True

    def _reset_swipe_position(self):
        """Reset the notification position after an incomplete swipe."""
        self.notification_box.set_margin_start(0)
        self.notification_box.set_margin_end(0)
        self.notification_box.set_opacity(1.0)
        self.resume_timeout()

    _DEFAULT_TIMEOUTS: ClassVar[dict[int, int]] = {0: 3000, 1: 8000, 2: 15000}

    def get_timeout(self) -> int:
        if self.config.get("respect_expire", True) and self._notification.timeout != -1:
            return self._notification.timeout

        timeout_config = self.config.get("timeout")
        if isinstance(timeout_config, dict):
            urgency = self._notification.urgency
            if urgency == 0:
                return timeout_config.get("low", self._DEFAULT_TIMEOUTS[0])
            elif urgency == 1:
                return timeout_config.get("normal", self._DEFAULT_TIMEOUTS[1])
            elif urgency == 2:
                return timeout_config.get("critical", self._DEFAULT_TIMEOUTS[2])

        # Fallback when timeout config is missing or not a dict
        return self._DEFAULT_TIMEOUTS.get(
            self._notification.urgency, self._DEFAULT_TIMEOUTS[1]
        )

    def pause_timeout(self):
        self.stop_timeout()

    def resume_timeout(self):
        """Resume the countdown from where it left off after a pause."""
        if self._timeout_id is not None:
            return
        self._last_tick_time = GLib.get_monotonic_time()
        self._timeout_id = self.progress_timeout.add_tick_callback(self._tick_callback)

    def on_hover(self, *_):
        self.pause_timeout()
        self.set_pointer_cursor(self, "hand2")

        if self.config.get("dismiss_on_hover", False):
            self.close_notification()

    def on_unhover(self, *_):
        self.resume_timeout()
        self.set_pointer_cursor(self, "arrow")

    @staticmethod
    def set_pointer_cursor(widget: Widget, cursor_name: str):
        window = widget.get_window()
        if window:
            cursor = Gdk.Cursor.new_from_name(widget.get_display(), cursor_name)
            window.set_cursor(cursor)


class NotificationRevealer(Revealer):
    """A widget to reveal a notification with open/close animations."""

    def __init__(self, config: dict, notification: Notification, **kwargs):
        self.notification_box = NotificationWidget(config, notification)
        self.timeout = self.notification_box.get_timeout()
        self._notification = notification
        self._is_closing = False
        self._closed_handler_id = None

        super().__init__(
            name="notification-revealer",
            child=self.notification_box,
            transition_duration=config.get("transition_duration", 200),
            transition_type=config.get("transition_type", "slide-up"),
            **kwargs,
        )

        self.connect("notify::child-revealed", self.on_child_revealed)

        self._closed_handler_id = self._notification.connect("closed", self.on_resolved)

    def replace_notification(self, notification: Notification):
        config = self.notification_box.config
        self.notification_box.stop_timeout()
        self.notification_box.destroy()

        self._notification = notification
        self.notification_box = NotificationWidget(
            config,
            notification,
        )
        self.timeout = self.notification_box.get_timeout()

        self.add(self.notification_box)

        self._closed_handler_id = self._notification.connect("closed", self.on_resolved)

        if not self.get_reveal_child():
            self._is_closing = False
            self.set_reveal_child(True)
        if self.timeout > 0:
            self.notification_box.start_timeout()

    def on_child_revealed(self, *_):
        if not self.get_child_revealed():
            self.destroy()
        else:
            if self.timeout > 0:
                self.notification_box.start_timeout()

    def on_resolved(self, notification, *_):
        if notification is not self._notification:
            return
        if self._is_closing:
            return
        self._is_closing = True
        # Trigger close animation - destroy happens in on_child_revealed
        self.set_reveal_child(False)


class CopyCodeButton(HoverButton):
    """A button that copies a one-time code from the body to the clipboard,
    then dismisses the notification (SwayNC-inspired)."""

    def __init__(
        self,
        code: str,
        action_number: int,
        total_actions: int,
        notification: Notification | None = None,
        **kwargs,
    ):
        super().__init__(
            label=f'Copy "{code}"',
            h_expand=True,
            on_clicked=self.on_click,
            style_classes="notification-action",
            **kwargs,
        )

        self.code = code
        self._notification = notification

        if action_number == 0:
            self.add_style_class("start-action")
        elif action_number == total_actions - 1:
            self.add_style_class("end-action")
        else:
            self.add_style_class("middle-action")

    def on_click(self, *_):
        helpers.copy_to_clipboard_async(self.code)
        if self._notification:
            self._notification.close("dismissed-by-user")


class ActionButton(HoverButton):
    """A button widget to represent a notification action."""

    def __init__(
        self,
        action: NotificationAction,
        action_number: int,
        total_actions: int,
        **kwargs,
    ):
        super().__init__(
            label=action.label,
            h_expand=True,
            on_clicked=self.on_click,
            style_classes="notification-action",
            **kwargs,
        )

        self.action = action

        if action_number == 0:
            self.add_style_class("start-action")
        elif action_number == total_actions - 1:
            self.add_style_class("end-action")
        else:
            self.add_style_class("middle-action")

    def on_click(self, *_):
        self.action.invoke()
        self.action.parent.close("dismissed-by-user")

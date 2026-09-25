"""Tests for the shared notification card builders.

The Fabric widgets are replaced with mocks: only the composition contract
matters here (child order, packed-end order, wiring), and real widgets need a
display.
"""

import unittest
from unittest import mock

from shared import notification_card
from tests.helpers import make_notification


class HeaderTest(unittest.TestCase):
    """``header()`` packs leading children left and trailing controls right."""

    def setUp(self):
        box_patcher = mock.patch.object(notification_card, "Box")
        self.box = box_patcher.start()
        self.addCleanup(box_patcher.stop)
        self.header_box = self.box.return_value

    def _packed_end(self) -> list:
        return [call.args[0] for call in self.header_box.pack_end.call_args_list]

    def test_leading_children_keep_their_order(self):
        leading = ["icon", "summary"]

        notification_card.header(leading=leading)

        self.assertEqual(tuple(leading), self.header_box.children)
        self.header_box.pack_end.assert_not_called()

    def test_trailing_controls_are_packed_in_visual_order(self):
        timestamp, close = "timestamp", "close"

        # pack_end prepends, so the builder must feed it back-to-front for
        # the header to read timestamp-then-close.
        notification_card.header(leading=["summary"], trailing=[timestamp, close])

        self.assertEqual([close, timestamp], self._packed_end())

    def test_trailing_defaults_to_empty(self):
        notification_card.header(leading=["summary"])

        self.header_box.pack_end.assert_not_called()

    def test_extra_props_reach_the_box(self):
        notification_card.header(
            leading=["summary"],
            spacing=4,
            style_classes="notification-group-header",
            name="deck",
        )

        self.box.assert_called_once_with(
            spacing=4,
            orientation="h",
            style_classes="notification-group-header",
            name="deck",
        )


class AppIconTest(unittest.TestCase):
    """``app_icon()`` resolves the icon and shares one header size."""

    def setUp(self):
        image_patcher = mock.patch.object(notification_card, "Image")
        self.image = image_patcher.start()
        self.addCleanup(image_patcher.stop)

        resolve_patcher = mock.patch.object(
            notification_card, "resolve_notification_icon", return_value="pixbuf"
        )
        self.resolve = resolve_patcher.start()
        self.addCleanup(resolve_patcher.stop)

    def test_resolves_at_the_shared_size(self):
        notification = make_notification()

        notification_card.app_icon(notification)

        self.resolve.assert_called_once_with(
            notification, notification_card.APP_ICON_SIZE
        )
        self.image.assert_called_once_with(
            pixbuf="pixbuf",
            size=notification_card.APP_ICON_SIZE,
            v_align="center",
            style_classes="app-icon",
        )

    def test_explicit_size_overrides_the_default(self):
        notification_card.app_icon(make_notification(), size=40)

        self.assertEqual(40, self.image.call_args.kwargs["size"])


class CloseButtonTest(unittest.TestCase):
    """``close_button()`` wires the dismiss handler and tooltip through."""

    def setUp(self):
        button_patcher = mock.patch.object(notification_card, "Button")
        self.button = button_patcher.start()
        self.addCleanup(button_patcher.stop)

    def test_default_style_classes(self):
        on_clicked = mock.Mock()

        notification_card.close_button(on_clicked, tooltip_text="Dismiss")

        _, kwargs = self.button.call_args
        self.assertEqual(on_clicked, kwargs["on_clicked"])
        self.assertEqual("Dismiss", kwargs["tooltip_text"])
        self.assertEqual(["close-button"], kwargs["style_classes"])
        self.assertEqual("close-button", kwargs["name"])

    def test_extra_style_classes_are_appended(self):
        notification_card.close_button(
            mock.Mock(), style_classes=["close-button", "group-clear-button"]
        )

        _, kwargs = self.button.call_args
        self.assertEqual(
            ["close-button", "group-clear-button"], kwargs["style_classes"]
        )


if __name__ == "__main__":
    unittest.main()

"""Tests for the WM-client helpers in ``utils/hyprland.py``.

Dock and taskbar each parsed ``j/clients``, fetched the active address and
filtered the entries themselves. That plumbing now lives on the service, so
the filtering rules are pinned here once instead of per widget.
"""

import unittest
from unittest import mock

from utils.hyprland import HyprlandClient, HyprlandService

NORMAL = {"address": "0x1000", "class": "firefox", "workspace": {"id": 2}}
SPECIAL = {"address": "0x2000", "class": "kitty", "workspace": {"id": -98}}
OTHER_WORKSPACE = {"address": "0x5000", "class": "obs", "workspace": {"id": 7}}


def make_service() -> HyprlandService:
    service = HyprlandService.__new__(HyprlandService)
    service._connection = mock.Mock()
    return service


def addresses(clients) -> list:
    return [client.get_address_str() for client in clients]


class GetWmClientsTest(unittest.TestCase):
    """``get_wm_clients`` wraps the usable entries of a ``j/clients`` reply."""

    def setUp(self):
        self.service = make_service()

    def test_clients_are_wrapped_with_the_active_flag(self):
        (client,) = self.service.get_wm_clients([NORMAL], "0x1000")

        self.assertIsInstance(client, HyprlandClient)
        self.assertTrue(client.get_activated())

    def test_a_client_without_workspace_info_is_dropped(self):
        orphan = {"address": "0x3000", "class": "obs"}

        self.assertEqual([], self.service.get_wm_clients([orphan], None))

    def test_special_workspace_clients_shown_by_default(self):
        self.assertEqual(
            ["0x2000"], addresses(self.service.get_wm_clients([SPECIAL], None))
        )

    def test_special_workspace_clients_hidden_on_request(self):
        clients = self.service.get_wm_clients([SPECIAL], None, hide_special=True)

        self.assertEqual([], clients)

    def test_special_workspace_without_id_is_hidden_when_enabled(self):
        modern = {
            "address": "0x4000",
            "class": "org.kde.ktorrent",
            "workspace": {"type": "special", "name": "special:special"},
        }

        clients = self.service.get_wm_clients([modern], None, hide_special=True)

        self.assertEqual([], clients)

    def test_ignored_and_missing_app_ids_are_dropped(self):
        no_class = {"address": "0x6000", "workspace": {"id": 2}}

        clients = self.service.get_wm_clients(
            [NORMAL, no_class], None, ignored=["firefox"]
        )

        self.assertEqual([], clients)

    def test_workspace_id_restricts_the_list(self):
        clients = self.service.get_wm_clients(
            [NORMAL, OTHER_WORKSPACE], None, workspace_id=7
        )

        self.assertEqual(["0x5000"], addresses(clients))

    def test_no_workspace_id_keeps_every_workspace(self):
        clients = self.service.get_wm_clients([NORMAL, OTHER_WORKSPACE], None)

        self.assertEqual(["0x1000", "0x5000"], addresses(clients))

    def test_a_failed_fetch_yields_no_clients(self):
        self.assertEqual([], self.service.get_wm_clients(None, None))


class IndexClientsTest(unittest.TestCase):
    """``index_clients`` keys by normalized address."""

    def test_clients_are_keyed_by_normalized_address(self):
        service = make_service()
        unnamed = {"address": "1000", "class": "firefox", "workspace": {"id": 2}}

        indexed = service.index_clients(service.get_wm_clients([unnamed], None))

        self.assertEqual(["0x1000"], list(indexed))
        self.assertFalse(indexed["0x1000"].get_activated())

    def test_a_client_without_an_address_is_dropped(self):
        service = make_service()
        addressless = HyprlandClient({"class": "firefox", "workspace": {"id": 2}})

        self.assertEqual({}, service.index_clients([addressless]))


class ActiveWindowAddressTest(unittest.TestCase):
    """The active address is normalized and a bad reply becomes None."""

    def setUp(self):
        self.service = make_service()

    def reply(self, payload: bytes):
        callback = self.service._connection.send_command_async.call_args.args[1]
        callback(mock.Mock(reply=payload))

    def test_the_address_is_normalized(self):
        seen = []

        self.service.get_active_window_address_async(seen.append)
        self.reply(b'{"address": "1000"}')

        self.assertEqual(["0x1000"], seen)

    def test_a_missing_address_yields_none(self):
        seen = []

        self.service.get_active_window_address_async(seen.append)
        self.reply(b"{}")

        self.assertEqual([None], seen)

    def test_a_failed_parse_yields_none(self):
        seen = []

        self.service.get_active_window_address_async(seen.append)
        self.reply(b"not json")

        self.assertEqual([None], seen)


class ActiveWorkspaceTest(unittest.TestCase):
    """Widgets get the active workspace already parsed."""

    def setUp(self):
        self.service = make_service()

    def reply(self, payload: bytes):
        callback = self.service._connection.send_command_async.call_args.args[1]
        callback(mock.Mock(reply=payload))

    def test_the_parsed_workspace_is_delivered(self):
        seen = []

        self.service.get_active_workspace_async(seen.append)
        self.reply(b'{"id": 2, "windows": 0}')

        self.assertEqual([{"id": 2, "windows": 0}], seen)

    def test_a_failed_parse_delivers_an_empty_dict(self):
        """``parse_hyprland_reply`` logs and returns {} rather than raising."""
        seen = []

        self.service.get_active_workspace_async(seen.append)
        self.reply(b"not json")

        self.assertEqual([{}], seen)


if __name__ == "__main__":
    unittest.main()

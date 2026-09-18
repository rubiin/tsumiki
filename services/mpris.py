# Standard library imports
import gi

# Fabric imports
from fabric.core.service import Property, Service, Signal
from fabric.utils import GLib, bulk_connect, logger

from utils.exceptions import PlayerctlImportError
from utils.functions import safe_disconnect

try:
    gi.require_version("Playerctl", "2.0")
    from gi.repository import Gio, Playerctl
except ValueError:
    raise PlayerctlImportError()

_PLAYBACK_STATUS_MAP = {
    Playerctl.PlaybackStatus.PAUSED: "paused",
    Playerctl.PlaybackStatus.PLAYING: "playing",
    Playerctl.PlaybackStatus.STOPPED: "stopped",
}
_LOOP_STATUS_MAP = {
    Playerctl.LoopStatus.NONE: "none",
    Playerctl.LoopStatus.TRACK: "track",
    Playerctl.LoopStatus.PLAYLIST: "playlist",
}
_LOOP_STATUS_REVERSE_MAP = {
    "none": Playerctl.LoopStatus.NONE,
    "track": Playerctl.LoopStatus.TRACK,
    "playlist": Playerctl.LoopStatus.PLAYLIST,
}


class MprisPlayer(Service):
    """A service to manage a mpris player."""

    @Signal
    def exit(self, value: bool) -> bool: ...

    @Signal
    def changed(self) -> None: ...

    def __init__(
        self,
        player: Playerctl.Player,
        **kwargs,
    ):
        self._signal_connectors: dict = {}
        self._player: Playerctl.Player = player
        # Local (non-DBus) read, used to check name ownership safely.
        self._player_name: str = player.get_property("player-name")  # type: ignore
        super().__init__(**kwargs)
        for sn in ["playback-status", "loop-status", "shuffle"]:
            self._signal_connectors[sn] = self._player.connect(
                sn,
                lambda *args, sn=sn: self.notifier(sn, args),
            )

        self._signal_connectors["exit"] = self._player.connect(
            "exit",
            self.on_player_exit,
        )
        self._signal_connectors["metadata"] = self._player.connect(
            "metadata",
            lambda *_: self.update_status(),
        )
        GLib.idle_add(self.update_status_once)

    def _alive(self) -> bool:
        """Return whether the player's MPRIS bus name is currently owned.

        libplayerctl's synchronous getters call ``g_error()`` (which aborts
        the whole process, before Python can catch anything) when the
        player's DBus name is gone - e.g. while a player like VLC restarts
        its MPRIS service when opening a new file. Check name ownership
        first so callers can fall back to safe defaults instead.
        """
        if self._player is None:
            return False
        try:
            connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            result = connection.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "NameHasOwner",
                GLib.Variant("(s)", (f"org.mpris.MediaPlayer2.{self._player_name}",)),
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            return bool(result.unpack()[0])
        except Exception:
            return False

    def _notify_property(self, prop):
        if self.get_property(prop) is not None:
            self.notifier(prop)

    def update_status(self):
        # schedule each notifier asynchronously.
        # Guard: if the player has already exited, skip entirely.
        if self._player is None:
            return

        for prop in [
            "metadata",
            "title",
            "artist",
            "arturl",
            "length",
        ]:
            GLib.idle_add(lambda p=prop: (self._notify_property(p), False))
        for prop in [
            "can-seek",
            "can-pause",
            "can-shuffle",
            "can-go-next",
            "can-go-previous",
        ]:
            GLib.idle_add(lambda p=prop: (self.notifier(p), False))

    def _notify_all(self):
        for prop in self.list_properties():  # type: ignore
            self.notifier(prop.name)
        return False

    def update_status_once(self):
        # schedule notifier calls for each property

        GLib.idle_add(self._notify_all, priority=GLib.PRIORITY_DEFAULT_IDLE)

    def _notify_and_emit(self, name):
        self.notify(name)
        self.emit("changed")
        return False

    def notifier(self, name: str, args=None):
        GLib.idle_add(self._notify_and_emit, name, priority=GLib.PRIORITY_DEFAULT_IDLE)

    def on_player_exit(self, player):
        # Null out self._player immediately so that any pending idle callbacks
        # from update_status() that try to read metadata/properties see None
        # instead of talking to a dead DBus service (which aborts the process).
        dead_player = self._player
        self._player = None

        for id in list(self._signal_connectors.values()):
            safe_disconnect(dead_player, id)

        def _emit_exit_and_cleanup():
            self.emit("exit", True)
            del self._signal_connectors
            return False

        GLib.idle_add(_emit_exit_and_cleanup)

    def toggle_shuffle(self, *_):
        if self._alive() and self.can_shuffle:
            # schedule the shuffle toggle in the GLib idle loop
            GLib.idle_add(lambda: (setattr(self, "shuffle", not self.shuffle), False))
        # else do nothing

    def play_pause(self, *_):
        if self._alive() and self.can_pause:
            GLib.idle_add(
                lambda: (self._player.play_pause() if self._alive() else None, False)
            )

    def next(self, *_):
        if self._alive() and self.can_go_next:
            GLib.idle_add(
                lambda: (self._player.next() if self._alive() else None, False)
            )

    def previous(self, *_):
        if self._alive() and self.can_go_previous:
            GLib.idle_add(
                lambda: (self._player.previous() if self._alive() else None, False)
            )

    # Properties
    @Property(str, "readable")
    def player_name(self) -> int:
        if self._player is None:
            return ""
        return self._player.get_property("player-name")  # type: ignore

    @Property(int, "read-write", default_value=0)
    def position(self) -> int:
        if not self._alive():
            return 0
        return self._player.get_property("position")  # type: ignore

    @position.setter
    def position(self, new_pos: int):
        if self._alive():
            self._player.set_position(new_pos)

    @Property(object, "readable")
    def metadata(self) -> dict:
        if not self._alive():
            return {}
        return self._player.get_property("metadata")  # type: ignore

    @Property(str or None, "readable")
    def arturl(self) -> str | None:
        if "mpris:artUrl" in self.metadata.keys():  # type: ignore  # noqa: SIM118
            return self.metadata["mpris:artUrl"]  # type: ignore
        return None

    @Property(str or None, "readable")
    def length(self) -> str | None:
        if "mpris:length" in self.metadata.keys():  # type: ignore  # noqa: SIM118
            return self.metadata["mpris:length"]  # type: ignore
        return None

    @Property(str, "readable")
    def artist(self) -> str:
        if not self._alive():
            return ""
        artist = self._player.get_artist()  # type: ignore
        if isinstance(artist, (list, tuple)):
            return ", ".join(artist)
        return artist

    @Property(str, "readable")
    def album(self) -> str:
        if not self._alive():
            return ""
        return self._player.get_album()  # type: ignore

    @Property(str, "readable")
    def title(self):
        if not self._alive():
            return ""
        return self._player.get_title()

    @Property(bool, "read-write", default_value=False)
    def shuffle(self) -> bool:
        if not self._alive():
            return False
        return self._player.get_property("shuffle")  # type: ignore

    @shuffle.setter
    def shuffle(self, do_shuffle: bool):
        if not self._alive():
            return
        self.notifier("shuffle")
        self._player.set_shuffle(do_shuffle)

    @Property(str, "readable")
    def playback_status(self) -> str:
        if not self._alive():
            return "unknown"
        return _PLAYBACK_STATUS_MAP.get(
            self._player.get_property("playback_status"), "unknown"
        )  # type: ignore

    @Property(str, "read-write")
    def loop_status(self) -> str:
        if not self._alive():
            return "unknown"
        return _LOOP_STATUS_MAP.get(self._player.get_property("loop_status"), "unknown")  # type: ignore

    @loop_status.setter
    def loop_status(self, status: str):
        if not self._alive():
            return
        loop_status = _LOOP_STATUS_REVERSE_MAP.get(status)
        self._player.set_loop_status(loop_status) if loop_status else None

    @Property(bool, "readable", default_value=False)
    def can_go_next(self) -> bool:
        if not self._alive():
            return False
        return self._player.get_property("can_go_next")  # type: ignore

    @Property(bool, "readable", default_value=False)
    def can_go_previous(self) -> bool:
        if not self._alive():
            return False
        return self._player.get_property("can_go_previous")  # type: ignore

    @Property(bool, "readable", default_value=False)
    def can_seek(self) -> bool:
        if not self._alive():
            return False
        return self._player.get_property("can_seek")  # type: ignore

    @Property(bool, "readable", default_value=False)
    def can_pause(self) -> bool:
        if not self._alive():
            return False
        return self._player.get_property("can_pause")  # type: ignore

    @Property(bool, "readable", default_value=False)
    def can_shuffle(self) -> bool:
        if not self._alive():
            return False
        try:
            self._player.set_shuffle(self._player.get_property("shuffle"))
            return True
        except Exception as e:
            logger.debug(f"[MprisPlayer] Player doesn't support shuffle: {e}")
            return False

    @Property(bool, "readable", default_value=False)
    def can_loop(self) -> bool:
        if not self._alive():
            return False
        try:
            self._player.set_loop_status(self._player.get_property("loop_status"))
            return True
        except Exception as e:
            logger.debug(f"[MprisPlayer] Player doesn't support loop: {e}")
            return False


class MprisPlayerManager(Service):
    """A service to manage mpris players."""

    @Signal
    def player_appeared(self, player: Playerctl.Player) -> Playerctl.Player: ...

    @Signal
    def player_vanished(self, player_name: str) -> str: ...

    def __init__(
        self,
        **kwargs,
    ):
        self._manager = Playerctl.PlayerManager.new()
        bulk_connect(
            self._manager,
            {
                "name-appeared": self.on_name_appeared,
                "name-vanished": self.on_name_vanished,
            },
        )
        self.add_players()
        super().__init__(**kwargs)

    def on_name_appeared(self, manager, player_name: Playerctl.PlayerName):
        logger.info(f"[MprisPlayer] {player_name.name} appeared")
        new_player = Playerctl.Player.new_from_name(player_name)
        manager.manage_player(new_player)
        self.emit("player-appeared", new_player)  # type: ignore

    def on_name_vanished(self, manager, player_name: Playerctl.PlayerName):
        logger.info(f"[MprisPlayer] {player_name.name} vanished")
        self.emit("player-vanished", player_name.name)  # type: ignore

    def add_players(self):
        for player in self._manager.get_property("player-names"):  # type: ignore
            self._manager.manage_player(Playerctl.Player.new_from_name(player))  # type: ignore

    @Property(object, "readable")
    def players(self):
        return self._manager.get_property("players")  # type: ignore

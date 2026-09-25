import os
import tempfile
import urllib.parse

from fabric.utils import GLib, bulk_connect, idle_add, logger
from fabric.widgets.box import Box

from services.mpris import MprisPlayer, MprisPlayerManager
from shared.media import PlayerBoxStack
from shared.mixins import PopoverMixin
from shared.scrollable_text import ScrollingLabel
from shared.widget_container import ButtonWidget
from utils.colors import Colors
from utils.constants import ASSETS_DIR, NEWLINE_RE
from utils.functions import char_limit_to_px, get_http_client, safe_disconnect
from utils.i18n import _


class MprisWidget(ButtonWidget, PopoverMixin):
    """A compact bar widget showing the currently playing track."""

    def __init__(self, **kwargs):
        super().__init__(name="mpris", **kwargs)

        self.player = None
        self._player_update_handlers: list[int] = []
        self._progress_timer_id: int | None = None

        self.default_cover = f"{ASSETS_DIR}/images/disk.png"

        # Scrolling track label
        self.label = ScrollingLabel(
            name="mpris-label",
            style_classes=["panel-text"],
            scroll_on_hover=True,
            max_width=char_limit_to_px(self, self.config.get("truncation_size", 30)),
        )

        # Cover art thumbnail
        self.cover = Box(
            name="mpris-cover",
            style=f"background-image: url('{self.default_cover}');",
        )

        # Progress bar — styled via SCSS (#mpris-progress)
        self.progress = Box(name="mpris-progress")
        self.progress_fill = Box(
            name="mpris-progress-fill",
            h_align="start",
        )
        self.progress.children = [self.progress_fill]

        self.meta_box = Box(
            name="mpris-meta-box",
            orientation="v",
            spacing=2,
            h_expand=True,
            v_align="start",
            children=[self.label, self.progress],
        )

        self._last_progress_pct: float | None = None
        self._last_temp_art_path: str | None = None
        self.exit = False
        self._set_default_values()
        self.container_box.children = [self.cover, self.meta_box]

        bulk_connect(
            self,
            {
                "enter-notify-event": self.on_hover_enter,
                "leave-notify-event": self.on_hover_leave,
            },
        )

        self.label_format = self.config.get("label_format", "{title} - {artist}")

        # Services
        self.mpris_manager = MprisPlayerManager()
        self._register_handlers(
            self.mpris_manager,
            {
                "player-appeared": self.on_player_appeared,
                "player-vanished": self.on_player_vanished,
            },
        )

        for player in self.mpris_manager.players:
            logger.info(
                f"{Colors.INFO}[PLAYER MANAGER] player found: "
                f"{player.get_property('player-name')}",
            )
            if player.props.player_name in self.config.get("ignore", []):
                continue
            self._set_player(player)
            break

        self.setup_popover(
            lambda: PlayerBoxStack(self.mpris_manager, config=self.config),
        )
        # The 1 Hz progress tick is started/stopped by get_current() from the
        # player's playback status, so there is nothing to start here.

    def _bind_player_updates(self):
        self._unbind_player_updates()
        if self.player is None:
            return

        metadata_signals = [
            "changed",
            "notify::metadata",
            "notify::title",
            "notify::arturl",
            "notify::length",
            "notify::playback-status",
        ]

        for signal_name in metadata_signals:
            self._player_update_handlers.append(
                self.player.connect(signal_name, lambda *_: self.get_current())
            )

    def _sync_progress_timer(self, playback_status):
        """Run the 1 Hz progress tick only while playback actually advances."""
        if playback_status == "playing":
            self._start_progress_timer()
        else:
            self._stop_progress_timer()

    def _start_progress_timer(self):
        if self._progress_timer_id is not None:
            return
        self._progress_timer_id = self._register_repeater(
            GLib.timeout_add(1000, self._on_progress_tick)
        )

    def _stop_progress_timer(self):
        if self._progress_timer_id is None:
            return
        GLib.source_remove(self._progress_timer_id)
        self._unregister_repeater(self._progress_timer_id)
        self._progress_timer_id = None

    def _on_progress_tick(self):
        if self.player and self.player.playback_status == "playing":
            self._update_progress()
        return True

    def _update_progress(self):
        show_progress = False
        self.meta_box.v_align = "start"
        playback_status = self.player.playback_status if self.player else None

        if playback_status not in {"playing", "paused"}:
            self.meta_box.v_align = "center"
            progress_pct = 0.0
        else:
            title = (self.player.title or "").strip()
            show_progress = playback_status in {"playing", "paused"} and bool(title)
            try:
                track_length = (
                    int(self.player.length) if self.player.length is not None else 0
                )
            except (TypeError, ValueError):
                track_length = 0

            try:
                position = (
                    int(self.player.position) if self.player.position is not None else 0
                )
            except (TypeError, ValueError):
                position = 0

            if track_length > 0:
                progress_pct = max(0.0, min(100.0, (position / track_length) * 100.0))
            else:
                progress_pct = 0.0

        self.progress.set_visible(show_progress)

        if not show_progress:
            self._last_progress_pct = None
            self.progress_fill.set_style("")
            return

        rounded = round(progress_pct, 1)
        if rounded == self._last_progress_pct:
            return

        self._last_progress_pct = rounded
        alloc_width = self.progress.get_allocated_width()
        if alloc_width > 0:
            fill_px = max(1, round(alloc_width * rounded / 100.0))
            self.progress_fill.set_style(f"min-width: {fill_px}px;")
        else:
            self.progress_fill.set_style("")
            # Widget not yet allocated -- retry on next idle so the bar
            # appears as soon as the layout pass assigns a width.
            # Reset the sentinel so the retry isn't short-circuited.
            self._last_progress_pct = None
            GLib.idle_add(self._update_progress)

    def _unbind_player_updates(self):
        if self.player is None:
            self._player_update_handlers.clear()
            return

        for handler_id in self._player_update_handlers:
            safe_disconnect(self.player, handler_id)
        self._player_update_handlers.clear()

    def _set_player(self, raw_player):
        self._unbind_player_updates()
        self._last_progress_pct = None
        self.player = MprisPlayer(raw_player)
        self._bind_player_updates()
        self.get_current()

    def on_player_appeared(self, manager, raw_player):
        if raw_player.props.player_name in self.config.get("ignore", []):
            return
        if self.player is None or self.player.playback_status != "playing":
            self._set_player(raw_player)

    def on_player_vanished(self, manager, player_name):
        if self.player is None or self.player.player_name != player_name:
            return
        self._unbind_player_updates()
        self.player = None
        # The fallback below re-evaluates the player, and get_current() syncs
        # the progress tick to whatever it finds (including no player at all).

        for raw_player in self.mpris_manager.players:
            if raw_player.props.player_name in self.config.get("ignore", []):
                continue
            self._set_player(raw_player)
            return
        self.get_current()

    def on_hover_enter(self, *_):
        self.label.on_enter_notify()
        return False

    def on_hover_leave(self, *_):
        self.label.on_leave_notify()
        return False

    def _set_artwork(self, art_url):
        if self.exit:
            return
        parsed = urllib.parse.urlparse(art_url)
        if parsed.scheme == "file":
            local_path = urllib.parse.unquote(parsed.path)
            self._update_art(local_path)
        elif parsed.scheme in ("http", "https"):
            GLib.Thread.new("download-artwork", self._download_artwork, art_url)
        else:
            self._update_art(art_url)

    def _download_artwork(self, art_url):
        if self.exit:
            return
        try:
            suffix = urllib.parse.urlparse(art_url).path.rsplit(".", 1)[-1] or ".png"
            response = get_http_client().get(art_url, timeout=5)
            old_temp_path = self._last_temp_art_path
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
                tf.write(response.content)
                local_path = tf.name
            self._last_temp_art_path = local_path
            if (
                old_temp_path
                and old_temp_path != local_path
                and os.path.exists(old_temp_path)
            ):
                try:
                    os.remove(old_temp_path)
                except OSError:
                    logger.debug(f"[Mpris] Failed to remove temp file: {old_temp_path}")
        except Exception:
            local_path = self.default_cover
        idle_add(self._update_art, local_path)

    def _update_art(self, image_path):
        if self.exit:
            if self._last_temp_art_path and os.path.exists(self._last_temp_art_path):
                try:
                    os.remove(self._last_temp_art_path)
                except OSError:
                    logger.debug(
                        f"[Mpris] Failed to remove temp: {self._last_temp_art_path}"
                    )
                self._last_temp_art_path = None
            return
        has_art = bool(image_path) and os.path.isfile(image_path)
        art_path = image_path if has_art else self.default_cover
        safe_url = art_path.replace("\\", "\\\\").replace("'", "\\'")
        self.cover.set_style(f"background-image: url('{safe_url}');")

    def get_current(self):
        if self.exit:
            return
        playback_status = self.player.playback_status if self.player else None
        # A paused/stopped player's position never advances, so the tick would
        # only re-render an unchanged progress bar.
        self._sync_progress_timer(playback_status)
        if playback_status not in {"playing", "paused"}:
            self._set_default_values()
            return

        self.show()
        title = NEWLINE_RE.sub(" ", self.player.title or "").strip()
        bar_label = title or _("widget.mpris.nothing_playing")

        try:
            label_text = self.label_format.format(
                title=title,
                artist=self.player.artist or "",
                album=self.player.album or "",
                name=self.player.player_name or "",
            )
        except (KeyError, ValueError, IndexError):
            label_text = title
        self.label.set_text(label_text)

        art_url = getattr(self.player, "arturl", None) or self.default_cover
        self._set_artwork(art_url)

        self._update_progress()

        self.set_tooltip_if_enabled(bar_label)

    def _set_default_values(self):
        self._last_progress_pct = None
        self.cover.set_style(f"background-image: url('{self.default_cover}');")
        self.label.set_text(_("widget.mpris.nothing_playing"))
        self.meta_box.v_align = "center"
        self.progress.set_visible(False)
        self.progress_fill.set_style("")
        if self.config.get("hide_when_no_player", True):
            self.hide()

    def destroy(self):
        self._stop_progress_timer()
        self._unbind_player_updates()
        self.exit = True
        if self._last_temp_art_path and os.path.exists(self._last_temp_art_path):
            try:
                os.remove(self._last_temp_art_path)
            except OSError:
                logger.debug(
                    f"[Mpris] Failed to remove temp file: {self._last_temp_art_path}"
                )
            self._last_temp_art_path = None
        return super().destroy()

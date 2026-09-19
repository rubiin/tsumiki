import tempfile
import urllib.parse

from fabric.utils import GdkPixbuf, GLib, GObject, bulk_connect, idle_add, logger, os
from fabric.widgets.box import Box
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack

from services.mpris import MprisPlayer, MprisPlayerManager
from shared.sinewave_slider import SineWaveSlider
from utils.constants import APP_DATA_DIRECTORY, ASSETS_DIR, NEWLINE_RE
from utils.functions import ensure_directory, get_http_client
from utils.i18n import _
from utils.icon_resolver import resolve_icon_pixbuf
from utils.icons import get_text_icon
from utils.widget_utils import nerd_font_icon

from .buttons import HoverButton


def _format_seconds(micro_seconds: int) -> str:
    seconds = int(micro_seconds / 1_000_000)
    minutes = seconds // 60
    rem = seconds % 60
    return f"{minutes}:{rem:02d}"


def _format_time_combined(position_us: int, length_us: int) -> str:
    return f"{_format_seconds(position_us)} / {_format_seconds(length_us)}"


# Luminance threshold above which artwork is considered light and dark text
# is needed for readability.
_LIGHT_ART_LUMINANCE_THRESHOLD = 0.5


def _average_luminance(pixbuf: GdkPixbuf.Pixbuf) -> float | None:
    """Average perceptual luminance of a pixbuf, normalized to 0..1."""
    n_channels = pixbuf.get_n_channels()
    if n_channels < 3:
        return None
    width = pixbuf.get_width()
    height = pixbuf.get_height()
    rowstride = pixbuf.get_rowstride()
    pixels = pixbuf.get_pixels()
    total = 0.0
    count = 0
    for y in range(height):
        row = y * rowstride
        for x in range(width):
            offset = row + x * n_channels
            total += (
                0.2126 * pixels[offset]
                + 0.7152 * pixels[offset + 1]
                + 0.0722 * pixels[offset + 2]
            )
            count += 1
    return total / count / 255 if count else None


class PlayerBoxStack(Box):
    """Manages multiple player instances with navigation dots inside each PlayerBox."""

    def __init__(self, mpris_manager: MprisPlayerManager, config, **kwargs):
        self.config = config
        ensure_directory(f"{APP_DATA_DIRECTORY}/media")

        self.player_stack = Stack(
            transition_type="slide-left-right",
            transition_duration=500,
            name="player-stack",
        )
        self.current_stack_pos = 0

        super().__init__(orientation="v", children=[self.player_stack])
        self.hide()

        self.mpris_manager = mpris_manager
        bulk_connect(
            self.mpris_manager,
            {
                "player-appeared": self.on_new_player,
                "player-vanished": self.on_lost_player,
            },
        )

        for player in self.mpris_manager.players:
            logger.info(
                f"[PLAYER MANAGER] player found: {player.get_property('player-name')}",
            )
            self.on_new_player(self.mpris_manager, player)

    def _sync_dots(self):
        count = len(self.player_stack.get_children())
        for child in self.player_stack.get_children():
            child.update_dots(count, self.current_stack_pos)

    def switch_to_player(self, index):
        count = len(self.player_stack.get_children())
        if index < 0 or index >= count:
            return
        self.current_stack_pos = index
        self.player_stack.set_visible_child(
            self.player_stack.get_children()[index],
        )
        self._sync_dots()

    def on_new_player(self, mpris_manager, player):
        player_name = player.props.player_name
        if player_name in self.config.get("ignore", []):
            return
        self.set_visible(True)
        player_box = PlayerBox(
            player=MprisPlayer(player), config=self.config, parent=self
        )
        player_box.connect("destroy", lambda *_: self._sync_dots())
        self.player_stack.children = [
            *self.player_stack.children,
            player_box,
        ]
        self._sync_dots()
        logger.info(
            f"[PLAYER MANAGER] adding new player: {player.get_property('player-name')}",
        )

    def on_lost_player(self, mpris_manager, player_name):
        logger.info(f"[PLAYER_MANAGER] Player Removed {player_name}")
        players: list = self.player_stack.get_children()
        if not players:
            self.hide()
            self.current_stack_pos = 0
            return
        if len(players) == 1 and player_name == players[0].player.player_name:
            self.hide()
            self.current_stack_pos = 0
            return
        if (
            self.current_stack_pos < len(players)
            and players[self.current_stack_pos].player.player_name == player_name
        ):
            self.current_stack_pos = max(0, self.current_stack_pos - 1)
            self.player_stack.set_visible_child(
                self.player_stack.get_children()[self.current_stack_pos],
            )
        self._sync_dots()


class PlayerBox(Box):
    """Glassmorphism player card: metadata, waveform, playback."""

    def __init__(self, player: MprisPlayer, config: dict, parent=None, **kwargs):
        super().__init__(
            name="player-box",
            orientation="v",
            spacing=0,
            **kwargs,
        )

        self.player: MprisPlayer = player
        self.parent = parent
        self.config = config
        self.fallback_cover_path = f"{ASSETS_DIR}/images/disk.png"
        self._last_temp_art_path: str | None = None
        self._seekbar_timer_id: int | None = None
        self.exit = False

        # ─── Track Info ───
        self.title_label = Label(
            name="player-title",
            label=_("widget.mpris.no_title"),
            max_chars_width=28,
            ellipsization="end",
            h_align="start",
        )
        self.player_icon = Image(
            name="player-icon",
            pixbuf=resolve_icon_pixbuf(player.player_name, 20),
            visible=self.config.get("show_player_icon", True),
        )
        self.title_row = Box(
            name="player-title-row",
            spacing=6,
            children=[self.player_icon, self.title_label],
        )
        self.artist_label = Label(
            name="player-artist",
            label=_("widget.mpris.no_artist"),
            max_chars_width=28,
            ellipsization="end",
            h_align="start",
            visible=self.config.get("show_artist", True),
        )
        self.time_label = Label(
            name="player-time",
            label="0:00 / 0:00",
            h_align="start",
            visible=self.config.get("show_time", True),
        )

        for prop, widget in [
            ("title", self.title_label),
            ("artist", self.artist_label),
        ]:
            fallback = f"No {prop.title()}"
            self.player.bind_property(
                prop,
                widget,
                "label",
                GObject.BindingFlags.DEFAULT,
                lambda _, x, f=fallback: NEWLINE_RE.sub(" ", x) if x else f,
            )

        # ─── Progress Bar ───
        self.progress_bar = SineWaveSlider(
            name="player-slider", h_expand=True, value=0.0
        )

        # ─── Bottom Controls Row ───
        prev_icon = nerd_font_icon(
            icon=get_text_icon("mpris.previous"),
            props={"style_classes": ["player-icon-sm"]},
        )
        self.prev_btn = HoverButton(
            name="player-prev",
            child=prev_icon,
            on_clicked=self.player.previous,
        )
        self.player.bind_property("can_go_previous", self.prev_btn, "sensitive")

        next_icon = nerd_font_icon(
            icon=get_text_icon("mpris.next"),
            props={"style_classes": ["player-icon-sm"]},
        )
        self.next_btn = HoverButton(
            name="player-next",
            child=next_icon,
            on_clicked=self.player.next,
        )
        self.player.bind_property("can_go_next", self.next_btn, "sensitive")

        shuffle_icon = nerd_font_icon(
            icon=get_text_icon("mpris.shuffle"),
            props={"style_classes": ["player-icon-sm"]},
        )
        self.shuffle_btn = HoverButton(
            name="player-shuffle",
            child=shuffle_icon,
            on_clicked=self.player.toggle_shuffle,
        )
        self.player.bind_property("can_shuffle", self.shuffle_btn, "sensitive")

        self.controls_row = Box(
            name="player-controls-row",
            spacing=6,
            v_align="center",
            h_expand=True,
            children=[
                self.prev_btn,
                self.progress_bar,
                self.next_btn,
                self.shuffle_btn,
            ],
        )

        # ─── Center Column ───
        self.meta_col = Box(
            name="player-meta-col",
            orientation="v",
            spacing=3,
            v_align="center",
            h_expand=True,
            children=[
                self.title_row,
                self.artist_label,
                self.time_label,
            ],
        )

        # ─── Play/Pause Button ───
        self.play_pause_icon = nerd_font_icon(
            icon=get_text_icon("mpris.paused"),
            props={"style_classes": ["player-icon-lg"]},
        )
        self.play_pause_btn = HoverButton(
            name="player-play-pause",
            child=self.play_pause_icon,
            on_clicked=self.player.play_pause,
            v_align="start",
        )
        self.player.bind_property("can_pause", self.play_pause_btn, "sensitive")

        # ─── Main Row ───
        self.main_row = Box(
            name="player-main-row",
            spacing=12,
            children=[self.meta_col, self.play_pause_btn],
        )

        # ─── Player Dot Navigation ───
        self.dot_box = Box(
            name="player-dot-box",
            spacing=4,
            h_align="center",
        )

        self.children = [self.main_row, self.controls_row, self.dot_box]

        # ─── Signals ───
        bulk_connect(
            self.player,
            {
                "exit": self.on_player_exit,
                "notify::playback-status": self.on_playback_change,
                "notify::metadata": self.on_metadata,
                "notify::shuffle": self.on_shuffle_change,
            },
        )

        # Seed the seekbar/time label with the current playback state so the
        # bar starts at the track position instead of mid-widget, then keep
        # ticking; on_metadata restarts this timer on track changes.
        self._move_seekbar()
        self._seekbar_timer_id = GLib.timeout_add(1000, self._move_seekbar)

    # ─── Metadata ─────────────────────────────────────────────────────────────

    def on_metadata(self, *_):
        self._set_image()
        length = self.player.length
        if length:
            pos = self.player.position or 0
            self.time_label.set_label(_format_time_combined(pos, length))
        self._stop_seekbar_timer()
        self._seekbar_timer_id = GLib.timeout_add(1000, self._move_seekbar)

    def _set_image(self, *_):
        art_url = self.player.arturl
        if not art_url:
            self._update_art(self.fallback_cover_path)
            return
        parsed = urllib.parse.urlparse(art_url)
        if parsed.scheme == "file":
            local_arturl = urllib.parse.unquote(parsed.path)
            self._update_art(local_arturl)
        elif parsed.scheme in ("http", "https"):
            GLib.Thread.new("download-artwork", self._download_and_set_artwork, art_url)
        else:
            self._update_art(art_url)

    def _download_and_set_artwork(self, arturl):
        try:
            parsed = urllib.parse.urlparse(arturl)
            suffix = os.path.splitext(parsed.path)[1] or ".png"
            response = get_http_client().get(arturl, timeout=5)
            old_temp_path = self._last_temp_art_path
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(response.content)
                local_arturl = temp_file.name
            self._last_temp_art_path = local_arturl
            if (
                old_temp_path
                and old_temp_path != local_arturl
                and os.path.exists(old_temp_path)
            ):
                try:
                    os.remove(old_temp_path)
                except OSError:
                    logger.debug(f"[Media] Failed to remove temp file: {old_temp_path}")
        except Exception:
            local_arturl = self.fallback_cover_path
        idle_add(self._update_art, local_arturl)

    def _update_art(self, image_path):
        url = (
            f"url('{image_path}')"
            if image_path and os.path.isfile(image_path)
            else f"url('{self.fallback_cover_path}')"
        )
        self.set_style(f"background-image: {url};")
        self._update_art_contrast(image_path)

    def _update_art_contrast(self, image_path):
        """Toggle text color overrides based on artwork brightness.

        Text colors come from the theme (generated from the wallpaper), so
        they can clash with light album art. Classify the artwork and let
        SCSS pick readable text colors via ``on-light-art``/``on-dark-art``.
        """
        if not image_path or not os.path.isfile(image_path):
            return
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(image_path, 16, 16)
            luminance = _average_luminance(pixbuf)
        except Exception:
            logger.debug(f"[Media] Failed to compute art luminance: {image_path}")
            return
        if luminance is None:
            return
        light_art = luminance > _LIGHT_ART_LUMINANCE_THRESHOLD
        for cls in ("on-light-art", "on-dark-art"):
            self.remove_style_class(cls)
        self.add_style_class("on-light-art" if light_art else "on-dark-art")

    def update_dots(self, count: int, active_index: int):
        """Rebuild dot navigation for player switching."""
        self.dot_box.children = []
        for i in range(count):
            dot = HoverButton(
                name="player-stack-button",
                style_classes="active" if i == active_index else [],
                on_clicked=lambda *_, idx=i: (
                    self.parent.switch_to_player(idx) if self.parent else None
                ),
            )
            self.dot_box.add(dot)
        self.dot_box.set_visible(count > 1)

    # ─── Playback Controls ──────────────────────────────────────────────────

    def on_shuffle_change(self, *_):
        if self.player.shuffle:
            self.shuffle_btn.add_style_class("active")
        else:
            self.shuffle_btn.remove_style_class("active")

    def on_playback_change(self, player, _status):
        status = player.get_property("playback-status")
        if status == "paused":
            self.play_pause_icon.set_label(get_text_icon("mpris.playing"))
            self.progress_bar.set_active(False)
        elif status == "playing":
            self.play_pause_icon.set_label(get_text_icon("mpris.paused"))
            self.progress_bar.set_active(True)

    def _move_seekbar(self, *_):
        if self.player is None or self.exit:
            self._seekbar_timer_id = None
            return False
        pos = self.player.position
        length = self.player.length
        if length:
            self.time_label.set_label(_format_time_combined(pos, length))
            self.progress_bar.set_value(pos / length if length > 0 else 0.0)
        return True

    def _stop_seekbar_timer(self):
        if self._seekbar_timer_id is not None:
            GLib.source_remove(self._seekbar_timer_id)
            self._seekbar_timer_id = None

    # ─── Lifecycle ──────────────────────────────────────────────────────────

    def on_player_exit(self, _, value):
        self.exit = value
        self._stop_seekbar_timer()
        self.destroy()

    def destroy(self):
        self._stop_seekbar_timer()
        if self._last_temp_art_path and os.path.exists(self._last_temp_art_path):
            try:
                os.remove(self._last_temp_art_path)
            except OSError:
                logger.debug(
                    f"[Media] Failed to remove temp file: {self._last_temp_art_path}"
                )
            finally:
                self._last_temp_art_path = None
        super().destroy()

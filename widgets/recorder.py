from services.screen_record import ScreenRecorderService
from shared.widget_container import ButtonWidget
from utils.constants import ASSETS_DIR
from utils.i18n import _
from utils.icons import get_text_icon
from utils.widget_utils import nerd_font_icon


class RecorderWidget(ButtonWidget):
    """A widget to record the system"""

    def __init__(self, **kwargs):
        super().__init__(name="recorder", **kwargs)

        # Initial UI setup
        self.recording_idle_image = nerd_font_icon(
            icon=get_text_icon("recorder", "󰻂"),
            props={"style_classes": ["panel-font-icon"]},
        )
        self.container_box.add(self.recording_idle_image)

        if self.config.get("tooltip"):
            self.set_tooltip_text(_("widget.recorder.stopped"))

        self.recorder_service = None

        self.connect("clicked", self.on_click)

        # Internal state
        self._recording_lottie = None
        self.initialized = False

    def lazy_init(self):
        """Initialize the recorder service if not already initialized."""
        if not self.initialized:
            self.recorder_service = ScreenRecorderService()
            self._register_handler(
                self.recorder_service,
                self.recorder_service.connect("recording", self._update_ui),
            )
            self.initialized = True

    @property
    def recording_ongoing_lottie(self):
        from shared.lottie import LottieAnimation, LottieAnimationWidget

        if self._recording_lottie is None:
            self._recording_lottie = LottieAnimationWidget(
                LottieAnimation.from_file(
                    f"{ASSETS_DIR}/icons/recording.json",
                ),
                scale=0.30,
                h_align="center",
                v_align="center",
            )
        return self._recording_lottie

    def on_click(self, *_):
        """Start or stop recording the screen."""
        self.lazy_init()

        if not self.initialized:
            return  # Early exit if script not available

        if self.recorder_service.is_recording:
            self.recorder_service.screenrecord_stop()
        else:
            self.recorder_service.screenrecord_start(config=self.config)

    def _update_ui(self, _sender, is_recording: bool):
        current_children = self.container_box.get_children()

        if is_recording:
            if self.recording_idle_image in current_children:
                self.container_box.remove(self.recording_idle_image)
                self.container_box.add(self.recording_ongoing_lottie)

            self.recording_ongoing_lottie.play_loop()

            if self.config.get("tooltip"):
                self.set_tooltip_text(_("widget.recorder.started"))
        else:
            if (
                self._recording_lottie
                and self.recording_ongoing_lottie in current_children
            ):
                self.container_box.remove(self.recording_ongoing_lottie)
                self.container_box.add(self.recording_idle_image)

                self.recording_ongoing_lottie.stop_play()

            if self.config.get("tooltip"):
                self.set_tooltip_text(_("widget.recorder.stopped"))

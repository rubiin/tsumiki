from datetime import datetime

from fabric.utils import Gtk, bulk_connect, cooldown, invoke_repeater, logger, time
from fabric.widgets.box import Box
from fabric.widgets.grid import Grid
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.svg import Svg

from services.weather import WeatherService
from shared.mixins import PopoverMixin
from shared.widget_container import BoxWidget, ButtonWidget
from utils.constants import ASSETS_DIR
from utils.functions import check_if_day, convert_to_12hr_format
from utils.i18n import _
from utils.weather_icons import WEATHER_ICONS
from utils.widget_utils import nerd_font_icon

weather_service = WeatherService()


class BaseWeatherWidget:
    """Base class for weather widgets."""

    def get_description(self):
        if not getattr(self, "current_weather", None):
            return ""
        return self.current_weather["weatherDesc"][0]["value"]

    def get_humidity(self):
        if not getattr(self, "current_weather", None):
            return ""
        return self.current_weather["humidity"] + "%"

    def sunrise_sunset_time(self) -> str:
        return f" {self.sunrise_time}  {self.sunset_time}"

    def update_app_data(self, data):
        """Update the weather data."""
        self.data = data

        # Get the current weather
        self.current_weather = self.data["current"]

        # Get the hourly forecast
        self.hourly_forecast = self.data["hourly"]

        self.sunrise_time = self.data["astronomy"]["sunrise"]
        self.sunset_time = self.data["astronomy"]["sunset"]

        return True

    def get_wind_speed(self):
        if not getattr(self, "current_weather", None):
            return ""
        if self.config.get("wind_speed_unit", "kmh") == "kmh":
            return self.current_weather["windspeedKmph"] + " Km/h"

        return self.current_weather["windspeedMiles"] + " Mph"

    def get_temperature(self):
        """Get the current temperature in the specified unit."""
        if not getattr(self, "current_weather", None):
            return ""

        if self.config.get("temperature_unit", "celsius") == "celsius":
            return self.current_weather["temp_C"] + "°C"

        return self.current_weather["temp_F"] + "°F"

    def get_temperature_hour(self, index):
        """Get the temperature for a specific hour in the specified unit."""

        if self.config.get("temperature_unit", "celsius") == "celsius":
            return self.hourly_forecast[index]["tempC"] + "°C"

        return self.hourly_forecast[index]["tempF"] + "°F"

    def get_label_text(self) -> str:
        """Render ``label_format`` against the current conditions."""
        return self.config.get("label_format", "{location}").format(
            location=self.data["location"],
            temperature=self.get_temperature(),
            condition=self.get_description(),
            humidity=self.get_humidity(),
            wind_speed=self.get_wind_speed(),
            sunrise=self.sunrise_time,
            sunset=self.sunset_time,
        )


class WeatherMenu(BoxWidget, BaseWeatherWidget):
    """A menu to display the weather information."""

    def __init__(
        self,
        config: dict,
        **kwargs,
    ):
        super().__init__(
            name="weather-menu",
            orientation="v",
            h_expand=True,
            spacing=5,
            **kwargs,
        )

        self.config = config

        self.next_values = None

        self.update_time = datetime.now()

        self.weather_icons_dir = f"{ASSETS_DIR}/icons/svg/weather"

        self.current_weather_image = Svg(
            svg_file=f"{self.weather_icons_dir}/clear-day.svg",
            v_align="start",
            h_align="start",
            size=100,
        )

        self.title_box = Grid(
            name="weather-header-grid",
            column_spacing=20,
        )

        self.location = Label(
            style_classes="header-label",
            h_align="start",
            label="",
        )

        self.weather_description = Label(
            style_classes="header-label",
            h_align="start",
            label="",
        )

        self.humidity = Label(
            style_classes="header-label",
            h_align="start",
            label="",
        )

        self.wind_speed = Label(
            style_classes="header-label",
            h_align="start",
            label="",
        )

        self.temperature = Label(
            style_classes="header-label",
            h_align="start",
            label="",
        )

        self.sunset_sunrise = Label(
            style_classes="header-label",
            h_align="start",
            name="sunrise-sunset",
            label="",
        )

        self.title_box.attach(
            self.current_weather_image,
            0,
            0,
            2,
            3,
        )

        self.title_box.attach(
            self.location,
            2,
            0,
            1,
            1,
        )

        self.title_box.attach(
            self.weather_description,
            2,
            1,
            1,
            1,
        )

        self.title_box.attach(
            self.sunset_sunrise,
            2,
            2,
            1,
            1,
        )

        self.title_box.attach(
            self.temperature,
            3,
            0,
            1,
            1,
        )

        self.title_box.attach(
            self.humidity,
            3,
            1,
            1,
            1,
        )

        self.title_box.attach(
            self.wind_speed,
            3,
            2,
            1,
            1,
        )

        # Create a grid to display the hourly forecast
        self.forecast_box = Grid(
            column_spacing=20,
            name="weather-grid",
        )

        self.children = (
            self.title_box,
            Gtk.Expander(
                name="weather-expander",
                visible=True,
                child=self.forecast_box,
                expanded=self.config.get("expanded", True),
            ),
        )

        weather_service.set_provider(self.config.get("provider", "open-meteo"))
        weather_service.get_weather_async(
            location=self.config.get("location", ""),
            ttl=self.config.get("interval", 3600),
            callback=self.update_data,
        )

        self._register_repeater(invoke_repeater(60000, self.update_widget))

    def update_data(self, data):
        if data is None:
            return
        self.update_app_data(data)

        self.update_widget(forced=True)

    def update_widget(self, *args, **kwargs):
        forced = kwargs.get("forced", False)

        if (
            getattr(self, "data", None) is None
            or getattr(self, "hourly_forecast", None) is None
        ):
            return

        # Check if the update time is more than 4 minute ago
        if (datetime.now() - self.update_time).total_seconds() < 60 and not forced:
            return

        logger.debug("[Weather] Updating weather widget")

        self.update_time = datetime.now()

        current_time = int(time.strftime("%H00"))

        if forced:
            self.current_weather_image.set_from_file(
                self.get_weather_asset(self.current_weather["weatherCode"]),
            )

            self.location.set_label(self.data["location"])
            self.weather_description.set_label(self.get_description())
            self.sunset_sunrise.set_label(self.sunrise_sunset_time())
            self.humidity.set_label(f"󰖎 {self.get_humidity()}")
            self.temperature.set_label(f"  {self.get_temperature()}")
            self.wind_speed.set_label(f" {self.get_wind_speed()}")

        self.next_values = self.hourly_forecast[:4]

        if current_time > 1200:
            self.next_values = self.hourly_forecast[4:8]

            # clear the forecast box
            for child in self.forecast_box.get_children():
                self.forecast_box.remove(child)
                child.destroy()

        # show next 4 hours forecast, run this once on boot and after 1200

        if forced or current_time > 1200:
            for col, value in enumerate(self.next_values):
                hour = Label(
                    style_classes="weather-forecast-time",
                    label=f"{convert_to_12hr_format(value['time'])}",
                    h_align="center",
                )
                icon = Svg(
                    svg_file=self.get_weather_asset(
                        value["weatherCode"],
                        convert_to_12hr_format(value["time"]),
                    ),
                    size=65,
                    h_align="center",
                    h_expand=True,
                    style_classes="weather-forecast-icon",
                )

                temp = Label(
                    style_classes="weather-forecast-temp",
                    label=self.get_temperature_hour(col),
                    h_align="center",
                )

                forecast_col = Box(
                    orientation="v",
                    spacing=5,
                    h_align="center",
                    children=[hour, icon, temp],
                )
                self.forecast_box.attach(forecast_col, col, 0, 1, 1)
        return True

    def get_weather_asset(self, code: int, time_str: str | None = None) -> str:
        is_day = check_if_day(
            current_time=time_str,
            sunrise_time=self.sunrise_time,
            sunset_time=self.sunset_time,
        )
        image_name = "image" if is_day else "image-night"
        return f"{self.weather_icons_dir}/{WEATHER_ICONS[str(code)][image_name]}.svg"


class WeatherWidget(ButtonWidget, BaseWeatherWidget, PopoverMixin):
    """A widget to display the current weather."""

    def __init__(
        self,
        **kwargs,
    ):
        # Initialize the Box with specific name and style
        super().__init__(
            name="weather",
            **kwargs,
        )

        self.weather_icon = nerd_font_icon(
            icon="󱣶",
            props={
                "style_classes": ["panel-font-icon", "weather-icon"],
            },
        )
        self.container_box.add(self.weather_icon)

        self.connect("button-press-event", self.on_button_press)

        self.setup_popover(
            lambda: WeatherMenu(config=self.config),
            connect_clicked=False,
            on_close_callback=lambda *_: self.remove_style_class("active"),
        )

        self.update_time = datetime.now()

        self.weather_label = Label(
            label=_("common.loading"),
            style_classes="panel-text",
        )

        self.revealer = Revealer(
            child=self.weather_label,
            transition_duration=self.config.get("reveal_duration", 500),
            transition_type="slide_right",
            reveal_child=not self.config.get("hover_reveal", True),
        )
        self.container_box.add(self.revealer)

        self._weather_color = None
        self._hover_color = "#080808"

        bulk_connect(
            self,
            {
                "enter-notify-event": self._on_hover_enter,
                "leave-notify-event": self._on_hover_leave,
            },
        )

        self._update_ui(forced=True)

        self._register_repeater(invoke_repeater(60000, self._update_ui))

    def update_data(self, data):
        self.update_time = datetime.now()

        if data is None:
            self.weather_label.set_label("")
            self.weather_icon.set_markup("")
            self.set_tooltip_if_enabled(_("widget.weather.error"))
            return

        # Get the current weather
        self.update_app_data(data)

        code = self.current_weather.get("weatherCode")
        if code is None:
            return
        weather_icon = WEATHER_ICONS[str(code)]

        text_icon = (
            weather_icon["icon"]
            if check_if_day(
                sunrise_time=self.sunrise_time, sunset_time=self.sunset_time
            )
            else weather_icon["icon-night"]
        )

        self._weather_color = weather_icon["color"]
        self._text_icon = text_icon
        self._label_text = self.get_label_text()

        self.weather_icon.set_markup(
            f'<span foreground="{self._weather_color}">{self._text_icon}</span>'
        )

        self.weather_label.set_markup(
            f'<span foreground="{self._weather_color}">{self._label_text}</span>'
        )

        # Update the tooltip with the city and weather condition if enabled
        tool_tip = f"{self.get_temperature()} {self.get_description()}"
        tool_tip += f"\n\n{weather_icon['quote']}"

        self.set_tooltip_if_enabled(tool_tip)

        return False

    def _on_hover_enter(self, *_args):
        """Switch markup colors to hover-friendly color."""
        if self._weather_color is None:
            return
        self.weather_icon.set_markup(
            f'<span foreground="{self._hover_color}">{self._text_icon}</span>'
        )
        self.weather_label.set_markup(
            f'<span foreground="{self._hover_color}">{self._label_text}</span>'
        )

    def _on_hover_leave(self, *_args):
        """Restore weather-specific markup colors."""
        if self._weather_color is None:
            return
        self.weather_icon.set_markup(
            f'<span foreground="{self._weather_color}">{self._text_icon}</span>'
        )
        self.weather_label.set_markup(
            f'<span foreground="{self._weather_color}">{self._label_text}</span>'
        )

    @cooldown(1)
    def on_button_press(self, _, event):
        if event.button == 1:
            self.show_popover()
        else:
            self._update_ui(forced=True)

    def _update_ui(self, *args, **kwargs):
        forced = kwargs.get("forced", False)

        # Check if the update time is more than 5 minutes ago, update the icon
        if (
            getattr(self, "current_weather", None) is not None
            and (datetime.now() - self.update_time).total_seconds() > 300
        ):
            weather_icon = WEATHER_ICONS[self.current_weather["weatherCode"]]
            self._weather_color = weather_icon["color"]
            self._text_icon = (
                weather_icon["icon"]
                if check_if_day(
                    sunrise_time=self.sunrise_time,
                    sunset_time=self.sunset_time,
                )
                else weather_icon["icon-night"]
            )

            self.weather_icon.set_markup(
                f'<span foreground="{self._weather_color}">{self._text_icon}</span>'
            )

        if (datetime.now() - self.update_time).total_seconds() < self.config.get(
            "interval", 3600
        ) and not forced:
            # Check if the update time is more than interval seconds ago
            return True  # Keep the repeater alive

        weather_service.set_provider(self.config.get("provider", "open-meteo"))
        weather_service.get_weather_async(
            location=self.config.get("location", ""),
            ttl=self.config.get("interval", 3600),
            callback=self.update_data,
        )

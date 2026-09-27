"""Tests for the weather service's retry loop.

The harness borrows the real fetch method: only the HTTP session and the sleep
are stubbed, so the backoff is observed rather than assumed.
"""

import unittest
from unittest import mock

import httpx

from services import weather as weather_module
from services.weather import WeatherService

_PAYLOAD = {
    "current_weather": {
        "time": "2024-01-01T10:00",
        "temperature": 10,
        "windspeed": 5,
        "weathercode": 0,
    },
    "hourly": {
        "time": ["2024-01-01T10:00", "2024-01-01T11:00"],
        "relative_humidity_2m": [50, 55],
        "temperature_2m": [10.0, 11.0],
        "weathercode": [0, 1],
    },
    "daily": {
        "sunrise": ["2024-01-01T06:00"],
        "sunset": ["2024-01-01T18:00"],
    },
}


class _OpenMeteoHarness:
    """Real Open-Meteo fetch logic with geocoding and transport stubbed out."""

    _fetch_openmeteo_weather = WeatherService._fetch_openmeteo_weather
    _map_weather_code = WeatherService._map_weather_code
    _get_weather_description = WeatherService._get_weather_description

    def __init__(self):
        self.api_url = "https://api.open-meteo.com/v1/forecast"

    def _geocode_location(self, _location):
        return (52.0, 13.0)


def _session(*payloads):
    session = mock.Mock()
    responses = []
    for payload in payloads:
        response = mock.Mock()
        response.json.return_value = payload
        responses.append(response)
    session.get.side_effect = responses
    return session


class RetryBackoffTest(unittest.TestCase):
    """Every attempt has to pay the backoff, not just the failing transport."""

    def setUp(self):
        patcher = mock.patch.object(weather_module.time, "sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def _fetch(self, *payloads, retries=3, delay=2.0):
        session = _session(*payloads)
        with mock.patch("utils.functions.get_http_client", return_value=session):
            result = _OpenMeteoHarness()._fetch_openmeteo_weather(
                "Berlin", retries=retries, delay=delay
            )
        return result, session

    def test_an_empty_payload_backs_off_before_retrying(self):
        """Three back-to-back requests is the opposite of a retry strategy."""
        result, session = self._fetch({}, {}, {})

        self.assertIsNone(result)
        self.assertEqual(3, session.get.call_count)
        self.assertEqual(
            [mock.call(2.0), mock.call(4.0), mock.call(6.0)],
            self.sleep.call_args_list,
        )

    def test_a_half_empty_payload_backs_off_too(self):
        result, session = self._fetch({"current_weather": {}}, {}, {})

        self.assertIsNone(result)
        self.assertEqual(3, session.get.call_count)
        self.assertEqual(3, self.sleep.call_count)

    def test_a_transient_empty_payload_still_returns_data(self):
        result, session = self._fetch({}, _PAYLOAD)

        self.assertIsNotNone(result)
        self.assertEqual(2, session.get.call_count)
        self.assertEqual([mock.call(2.0)], self.sleep.call_args_list)
        self.assertEqual("Berlin", result["location"])
        self.assertEqual("10", result["current"]["temp_C"])

    def test_a_transport_failure_still_backs_off(self):
        session = mock.Mock()
        session.get.side_effect = [
            httpx.RequestError("down"),
            httpx.RequestError("down"),
        ]
        with (
            mock.patch("utils.functions.get_http_client", return_value=session),
            mock.patch.object(weather_module, "logger") as logger,
        ):
            result = _OpenMeteoHarness()._fetch_openmeteo_weather(
                "Berlin", retries=2, delay=1.5
            )

        self.assertIsNone(result)
        self.assertEqual([mock.call(1.5), mock.call(3.0)], self.sleep.call_args_list)
        # loguru does not interpolate %s, so the cause has to be in the message.
        logged = " ".join(
            " ".join(str(part) for part in call.args)
            for call in logger.exception.call_args_list
        )
        self.assertIn("down", logged)


class GeocodeFailureLogTest(unittest.TestCase):
    """The offline path must log the reason instead of dropping the format arg."""

    def test_the_geocode_failure_logs_its_cause(self):
        session = mock.Mock()
        session.get.side_effect = httpx.RequestError("no network")
        service = WeatherService.__new__(WeatherService)
        service.geocode_url = "https://geocoding-api.open-meteo.com/v1/search"

        with (
            mock.patch("utils.functions.get_http_client", return_value=session),
            mock.patch.object(weather_module, "logger") as logger,
        ):
            coords = service._geocode_location("Berlin")

        self.assertIsNone(coords)
        logger.exception.assert_called_once()
        message = logger.exception.call_args.args[0]
        self.assertIn("no network", message)


if __name__ == "__main__":
    unittest.main()

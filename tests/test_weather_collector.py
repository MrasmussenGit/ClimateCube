import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from services import weather_collector


class WeatherCollectorTests(unittest.TestCase):
    def setUp(self):
        self.location = {
            "latitude": 40.7,
            "longitude": -74.0,
            "name": "Test location"
        }

    def test_api_url_requests_current_weather_and_daylight(self):
        parameters = parse_qs(urlparse(
            weather_collector.build_api_url(
                self.location,
                daylight_history_days=92
            )
        ).query)

        self.assertEqual(parameters["daily"], ["sunrise,sunset"])
        self.assertEqual(parameters["past_days"], ["92"])
        self.assertEqual(parameters["forecast_days"], ["7"])
        self.assertEqual(parameters["timezone"], ["GMT"])
        self.assertIn("cloud_cover", parameters["current"][0])

    def test_payload_parser_returns_observation_and_daylight_rows(self):
        payload = {
            "latitude": 40.71,
            "longitude": -73.99,
            "current": {
                "time": 1780315200,
                "temperature_2m": 20,
                "relative_humidity_2m": 50,
                "dew_point_2m": 10,
                "surface_pressure": 1000,
                "precipitation": 0,
                "wind_speed_10m": 5,
                "cloud_cover": 25,
                "weather_code": 1
            },
            "daily": {
                "time": [1780272000],
                "sunrise": [1780290000],
                "sunset": [1780344000]
            }
        }

        observation, daylight = weather_collector.parse_weather_payload(
            payload,
            self.location
        )

        self.assertEqual(observation["cloud_cover_pct"], 25)
        self.assertEqual(len(daylight), 1)
        self.assertLess(
            daylight[0]["sunrise_ts"],
            daylight[0]["sunset_ts"]
        )

    def test_storage_upserts_daylight_and_satisfies_backfill(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "weather.db"
            today = datetime.now(timezone.utc).date()
            daylight = []
            for days_ago in range(92):
                day = today - timedelta(days=days_ago)
                daylight.append({
                    "day": day.isoformat(),
                    "sunrise_ts": f"{day.isoformat()} 10:00:00",
                    "sunset_ts": f"{day.isoformat()} 22:00:00",
                    "latitude": self.location["latitude"],
                    "longitude": self.location["longitude"]
                })
            observation = {
                "observed_ts": f"{today.isoformat()} 12:00:00",
                "latitude": self.location["latitude"],
                "longitude": self.location["longitude"],
                "temperature_c": 20,
                "humidity_pct": 50,
                "dew_point_c": 10,
                "pressure_hpa": 1000,
                "precipitation_mm": 0,
                "wind_speed_kmh": 5,
                "cloud_cover_pct": 25,
                "weather_code": 1
            }

            with patch.object(
                weather_collector,
                "DB_FILE",
                database_path
            ):
                weather_collector.ensure_schema()
                weather_collector.store_weather(observation, daylight)
                self.assertFalse(
                    weather_collector.daylight_backfill_needed(self.location)
                )

            with sqlite3.connect(database_path) as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM weather_daylight"
                ).fetchone()[0]
            self.assertEqual(count, 92)


if __name__ == "__main__":
    unittest.main()

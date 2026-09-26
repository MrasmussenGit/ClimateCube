import unittest
from datetime import datetime

from services.database import match_daylight


class DatabaseDaylightTests(unittest.TestCase):
    def test_matches_daylight_by_date_provider_and_nearest_location(self):
        daylight_by_day = {
            "2026-06-01": [{
                "day": "2026-06-01",
                "sunrise_ts": "2026-06-01 09:30:00",
                "sunset_ts": "2026-06-02 00:15:00",
                "provider": "Open-Meteo",
                "latitude": 40.71,
                "longitude": -73.99
            }, {
                "day": "2026-06-01",
                "sunrise_ts": "2026-06-01 10:30:00",
                "sunset_ts": "2026-06-01 23:15:00",
                "provider": "Open-Meteo",
                "latitude": 42.0,
                "longitude": -75.0
            }]
        }

        result = match_daylight(
            daylight_by_day,
            datetime(2026, 6, 1, 12),
            {
                "provider": "Open-Meteo",
                "latitude": 40.7,
                "longitude": -74.0
            }
        )

        self.assertEqual(result, {
            "sunrise_ts": "2026-06-01 09:30:00",
            "sunset_ts": "2026-06-02 00:15:00"
        })

    def test_rejects_daylight_from_distant_location(self):
        result = match_daylight(
            {
                "2026-06-01": [{
                    "day": "2026-06-01",
                    "sunrise_ts": "2026-06-01 09:30:00",
                    "sunset_ts": "2026-06-02 00:15:00",
                    "provider": "Open-Meteo",
                    "latitude": 42.0,
                    "longitude": -75.0
                }]
            },
            datetime(2026, 6, 1, 12),
            {
                "provider": "Open-Meteo",
                "latitude": 40.7,
                "longitude": -74.0
            }
        )

        self.assertIsNone(result)

    def test_matches_previous_day_when_sunset_crosses_utc_midnight(self):
        result = match_daylight(
            {
                "2026-06-01": [{
                    "day": "2026-06-01",
                    "sunrise_ts": "2026-06-01 09:30:00",
                    "sunset_ts": "2026-06-02 00:30:00",
                    "provider": "Open-Meteo",
                    "latitude": 40.71,
                    "longitude": -73.99
                }]
            },
            datetime(2026, 6, 2, 0, 15),
            {
                "provider": "Open-Meteo",
                "latitude": 40.7,
                "longitude": -74.0
            }
        )

        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()

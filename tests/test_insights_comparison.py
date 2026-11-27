import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from services.web_server import app


def correlation_dataset():
    start = datetime(2026, 1, 1)
    observations = []

    for index in range(4):
        observations.append({
            "reading_time": (
                start + timedelta(minutes=index * 15)
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "indoor": {"temperature_c": 20 + index},
            "outdoor": {
                "temperature_c": 10 + index,
                "humidity_pct": None,
                "dew_point_c": None,
                "pressure_hpa": None,
                "precipitation_mm": None,
                "wind_speed_kmh": None,
                "cloud_cover_pct": None
            }
        })

    return {
        "observations": observations,
        "indoor_metrics": {
            "temperature_c": {
                "label": "Indoor temperature",
                "unit": "°C",
                "display_order": 10
            }
        },
        "sensor_bucket_count": len(observations),
        "aligned_bucket_count": len(observations)
    }


class InsightsComparisonTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.sensors = [
            {
                "sensor_id": 1,
                "sensor_name": "Garage",
                "active_flag": 1
            },
            {
                "sensor_id": 2,
                "sensor_name": "Bedroom",
                "active_flag": 1
            },
            {
                "sensor_id": 3,
                "sensor_name": "Hidden",
                "active_flag": 0
            }
        ]

    @patch("services.web_server.get_sensors")
    def test_comparison_page_lists_only_active_rooms(self, get_sensors):
        get_sensors.return_value = self.sensors

        response = self.client.get("/insights")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Garage", response.data)
        self.assertIn(b"Bedroom", response.data)
        self.assertNotIn(b">Hidden<", response.data)

    @patch("services.web_server.get_correlation_observations")
    @patch("services.web_server.get_sensors")
    def test_comparison_api_keeps_rooms_separate(
        self,
        get_sensors,
        get_correlation_observations
    ):
        get_sensors.return_value = self.sensors
        get_correlation_observations.return_value = correlation_dataset()

        response = self.client.get(
            "/api/insights?range=7d&timezone=UTC&sensor_id=2"
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["rooms"]), 1)
        self.assertEqual(payload["rooms"][0]["sensor"]["sensor_id"], 2)
        self.assertEqual(
            payload["rooms"][0]["relationship"]["id"],
            "temperature_c__temperature_c"
        )
        get_correlation_observations.assert_called_once_with(2, "7d")

    @patch("services.web_server.get_sensors")
    def test_comparison_api_rejects_unknown_sensor(self, get_sensors):
        get_sensors.return_value = self.sensors

        response = self.client.get(
            "/api/insights?range=30d&timezone=UTC&sensor_id=99"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Invalid sensor selection"
        )


if __name__ == "__main__":
    unittest.main()

import math
import unittest
from datetime import datetime, timedelta

from services.insights import analyze_correlations, pearson, spearman


class CorrelationTests(unittest.TestCase):
    def test_pearson_and_spearman(self):
        self.assertAlmostEqual(pearson([1, 2, 3], [2, 4, 6]), 1.0)
        self.assertAlmostEqual(pearson([1, 2, 3], [6, 4, 2]), -1.0)
        self.assertAlmostEqual(spearman([1, 2, 2, 4], [10, 20, 20, 40]), 1.0)
        self.assertIsNone(pearson([1, 1, 1], [2, 3, 4]))

    def test_analysis_finds_known_lag_and_daily_cycle(self):
        start = datetime(2026, 1, 1)
        outdoor_values = []

        for index in range(10 * 24 * 4):
            hour = index / 4
            outdoor_values.append(
                12 + 8 * math.sin(2 * math.pi * hour / 24)
                + 0.7 * math.sin(2 * math.pi * hour / 5)
            )

        observations = []
        for index, outdoor_temperature in enumerate(outdoor_values):
            delayed_index = max(0, index - 4)
            observations.append({
                "reading_time": (
                    start + timedelta(minutes=index * 15)
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "indoor": {
                    "temperature_c": 18 + 0.45 * outdoor_values[delayed_index]
                },
                "outdoor": {
                    "temperature_c": outdoor_temperature,
                    "humidity_pct": None,
                    "dew_point_c": None,
                    "pressure_hpa": None,
                    "precipitation_mm": None,
                    "wind_speed_kmh": None,
                    "cloud_cover_pct": None
                }
            })

        result = analyze_correlations({
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
        })

        relationship = result["relationships"][0]
        self.assertEqual(relationship["indoor_key"], "temperature_c")
        self.assertEqual(relationship["outdoor_key"], "temperature_c")
        self.assertEqual(relationship["lag"]["minutes"], 60)
        self.assertGreater(relationship["lag"]["correlation"], 0.99)
        self.assertGreater(result["daily_patterns"][0]["r_squared"], 0.8)
        self.assertEqual(len(result["daily_patterns"]), 1)
        self.assertEqual(result["coverage"]["aligned_percent"], 100.0)

    def test_analysis_can_limit_metrics_for_room_comparison(self):
        observations = []
        start = datetime(2026, 1, 1)

        for index in range(16):
            observations.append({
                "reading_time": (
                    start + timedelta(minutes=index * 15)
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "indoor": {
                    "temperature_c": 20 + index,
                    "humidity_pct": 40 + index
                },
                "outdoor": {
                    "temperature_c": 10 + index,
                    "humidity_pct": 50 + index,
                    "dew_point_c": None,
                    "pressure_hpa": None,
                    "precipitation_mm": None,
                    "wind_speed_kmh": None,
                    "cloud_cover_pct": None
                }
            })

        result = analyze_correlations(
            {
                "observations": observations,
                "indoor_metrics": {
                    "temperature_c": {
                        "label": "Indoor temperature",
                        "unit": "°C",
                        "display_order": 10
                    },
                    "humidity_pct": {
                        "label": "Indoor humidity",
                        "unit": "%",
                        "display_order": 20
                    }
                },
                "sensor_bucket_count": len(observations),
                "aligned_bucket_count": len(observations)
            },
            indoor_keys={"temperature_c"},
            outdoor_keys={"temperature_c"},
            include_daily_patterns=False,
            include_sunlight_effect=False
        )

        self.assertEqual(len(result["relationships"]), 1)
        self.assertEqual(
            result["relationships"][0]["id"],
            "temperature_c__temperature_c"
        )
        self.assertEqual(result["daily_patterns"], [])
        self.assertIsNone(result["sunlight_effect"])

    def test_sunlight_effect_controls_for_outdoor_temperature(self):
        observations = []
        start = datetime(2026, 6, 1)

        for day in range(3):
            for hour in range(8, 18):
                outdoor_temperature = 12 + hour - 8 + day * 0.3
                cloud_cover = (hour * 37 + day * 23) % 101
                indoor_temperature = (
                    18
                    + 0.4 * outdoor_temperature
                    - 2 * cloud_cover / 100
                )
                observations.append({
                    "reading_time": (
                        start + timedelta(days=day, hours=hour)
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    "indoor": {
                        "temperature_c": indoor_temperature
                    },
                    "outdoor": {
                        "temperature_c": outdoor_temperature,
                        "humidity_pct": None,
                        "dew_point_c": None,
                        "pressure_hpa": None,
                        "precipitation_mm": None,
                        "wind_speed_kmh": None,
                        "cloud_cover_pct": cloud_cover
                    }
                })

            observations.append({
                "reading_time": (
                    start + timedelta(days=day, hours=22)
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "indoor": {"temperature_c": 100},
                "outdoor": {
                    "temperature_c": 18,
                    "humidity_pct": None,
                    "dew_point_c": None,
                    "pressure_hpa": None,
                    "precipitation_mm": None,
                    "wind_speed_kmh": None,
                    "cloud_cover_pct": 100
                }
            })

        result = analyze_correlations({
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
        })

        effect = result["sunlight_effect"]
        self.assertEqual(effect["sample_count"], 30)
        self.assertAlmostEqual(effect["cloud_effect_c"], -2.0)
        self.assertAlmostEqual(effect["outdoor_coefficient"], 0.4)
        self.assertAlmostEqual(effect["r_squared"], 1.0)


if __name__ == "__main__":
    unittest.main()

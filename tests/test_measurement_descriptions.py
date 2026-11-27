import unittest

from services.database import get_measurement_description


class MeasurementDescriptionTests(unittest.TestCase):
    def test_gas_descriptions_include_relative_and_safety_guidance(self):
        keys = (
            "bme688_gas_resistance_ohms",
            "mics6814_reducing_ohms",
            "mics6814_oxidising_ohms",
            "mics6814_nh3_ohms"
        )

        for key in keys:
            with self.subTest(key=key):
                description = get_measurement_description(key, key)
                self.assertIn("relative", description.lower())
                self.assertTrue(
                    "alarm" in description.lower()
                    or "detector" in description.lower()
                )


if __name__ == "__main__":
    unittest.main()

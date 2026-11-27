import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, mock_open, patch


PICO_DIR = Path(__file__).resolve().parent.parent / "pico"


def load_pico_module(name):
    spec = importlib.util.spec_from_file_location("test_pico_" + name, PICO_DIR / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SensorRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.bus = Mock()
        self.bus.scan.return_value = [0x3c, 0x76]
        self.bus.readfrom_mem.return_value = b"\x60"
        self.driver = SimpleNamespace(values=("21.50C", "1006.26hPa", "41.57%"))
        self.machine = Mock()
        self.machine.I2C.return_value = self.bus
        self.bme280 = Mock()
        self.bme280.BME280.return_value = self.driver
        self.bme680 = Mock()
        self.modules = patch.dict("sys.modules", {
            "machine": self.machine,
            "bme280_float": self.bme280,
            "bme680": self.bme680
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.sensor = load_pico_module("sensor")

    def test_setup_and_scan_errors_return_unavailable_then_recover(self):
        for stage in ("setup", "scan"):
            with self.subTest(stage=stage):
                failing = self.machine.I2C if stage == "setup" else self.bus.scan
                failing.side_effect = OSError(5, "I2C failure")
                self.assertIsNone(self.sensor.GetTempData())
                self.assertIn("I2C setup/scan failed", self.sensor.get_error())
                self.assertIsNone(self.sensor.bme)
                failing.side_effect = None
                data = self.sensor.GetTempData()
                self.assertEqual(data["temperature_c"], 21.5)
                self.assertEqual(self.sensor.get_hardware(), ["BME280"])
                self.assertIsNone(self.sensor.get_error())
                self.sensor.bme = None

    def test_missing_sensor_records_scanned_addresses_and_reappears(self):
        self.bus.scan.return_value = [0x3c]
        self.assertIsNone(self.sensor.GetTempData())
        self.assertIn("No environmental sensor", self.sensor.get_error())
        self.assertIn("0x3c", self.sensor.get_error())
        self.bus.scan.return_value = [0x3c, 0x77]
        self.assertEqual(self.sensor.GetTempData()["humidity_pct"], 41.57)
        self.assertEqual(self.bme280.BME280.call_args.kwargs["address"], 0x77)
        self.assertIsNone(self.sensor.get_error())

    def test_initialization_failure_can_retry_without_losing_error(self):
        self.bus.readfrom_mem.side_effect = OSError(5, "read failed")
        self.assertIsNone(self.sensor.GetTempData())
        self.assertIn("Sensor initialization at 0x76 failed", self.sensor.get_error())
        self.bus.readfrom_mem.side_effect = None
        self.assertIsNotNone(self.sensor.GetTempData())
        self.assertIsNone(self.sensor.get_error())

    def test_conversion_timeout_discards_driver_and_reinitializes(self):
        class FailingDriver:
            @property
            def values(self):
                raise RuntimeError("Sensor BME280 not ready")

        self.bme280.BME280.side_effect = [FailingDriver(), self.driver]
        self.assertIsNone(self.sensor.GetTempData())
        self.assertIn("BME280 reading failed: Sensor BME280 not ready", self.sensor.get_error())
        self.assertIsNone(self.sensor.bme)
        self.assertEqual(self.sensor.get_hardware(), [])
        self.assertEqual(self.sensor.GetTempData()["pressure_hpa"], 1006.26)
        self.assertEqual(self.bme280.BME280.call_count, 2)
        self.assertIsNone(self.sensor.get_error())

    def test_bme688_values_and_measurements_are_preserved(self):
        self.bus.readfrom_mem.return_value = b"\x61"
        self.bme680.BME680_I2C.return_value = SimpleNamespace(
            temperature=22.5, pressure=1000.5, humidity=45.0, gas=12345
        )
        data = self.sensor.GetTempData()
        self.assertEqual(data["gas_resistance_ohms"], 12345)
        self.assertEqual(self.sensor.get_hardware(), ["BME688"])
        self.assertEqual(self.sensor.get_measurements(data)[-1]["value"], 12345)
        self.assertIsNone(self.sensor.get_error())


class DisplayRecoveryTests(unittest.TestCase):
    def test_shared_bus_setup_and_scan_failures_do_not_stop_warning_loop(self):
        for stage in ("setup", "scan"):
            with self.subTest(stage=stage):
                machine = Mock()
                machine.I2C.return_value.scan.return_value = [0x3c]
                failing = machine.I2C if stage == "setup" else machine.I2C.return_value.scan
                failing.side_effect = OSError(5, "bus unavailable")
                oled = Mock()
                with patch.dict("sys.modules", {
                    "machine": machine, "ssd1306": Mock(SSD1306_I2C=Mock(return_value=oled)),
                    "device": Mock()
                }), patch("builtins.print") as output:
                    display = load_pico_module("display")
                    self.assertFalse(display.show_sensor_not_detected())
                    self.assertIsNone(display.oled)
                    self.assertIn("bus unavailable", output.call_args.args[0])
                    failing.side_effect = None
                    self.assertTrue(display.show_sensor_not_detected())
                    oled.text.assert_any_call("Sensor read", 0, 22)
                    oled.text.assert_any_call("unavailable", 0, 38)


class MainRecoveryTests(unittest.TestCase):
    def test_repeated_failures_back_off_log_reason_and_resume_publishing(self):
        data = {
            "temperature_c": 21.5, "humidity_pct": 41.57,
            "pressure_hpa": 1006.26, "gas_resistance_ohms": None
        }
        reading = {"environmental": data, "hardware": ["BME280"], "measurements": []}
        manager = Mock()
        manager.read.side_effect = [None, None, None, reading, StopIteration("test complete")]
        manager.get_error.return_value = "BME280 reading failed: timeout"
        wlan = Mock()
        wlan.ifconfig.return_value = ("192.168.1.49", "", "", "")
        clock = Mock()
        clock.datetime.return_value = (2026, 11, 2, 0, 14, 0, 0, 0)
        time = Mock()
        time.ticks_ms.return_value = 0
        time.ticks_add.side_effect = lambda value, delta: value + delta
        time.ticks_diff.return_value = 0
        mqtt = Mock()
        display = Mock()
        modules = {
            "wifi": Mock(connect=Mock(return_value=wlan)), "ntpTime": Mock(),
            "sensor_manager": manager, "time": time, "mqttClient": mqtt,
            "display": display, "device": Mock(), "controls": Mock(),
            "machine": Mock(RTC=Mock(return_value=clock)),
            "config": SimpleNamespace(READING_INTERVAL_SEC=300),
            "os": Mock(stat=Mock(side_effect=OSError("no log yet")))
        }
        with patch.dict("sys.modules", modules), patch("builtins.open", mock_open()), patch("builtins.print") as output:
            with self.assertRaisesRegex(StopIteration, "test complete"):
                load_pico_module("main")
        self.assertEqual([call.args[0] for call in time.sleep.call_args_list], [10, 30, 60])
        self.assertEqual(display.show_sensor_not_detected.call_count, 3)
        mqtt.publish_reading.assert_called_once()
        payload = mqtt.publish_reading.call_args.args[0]
        self.assertEqual(payload["temperature_c"], 21.5)
        self.assertEqual(payload["timestamp"], "2026-11-02T14:00:00")
        messages = [call.args[0] for call in output.call_args_list]
        self.assertTrue(any("BME280 reading failed: timeout" in message for message in messages))
        self.assertIn("Environmental sensor recovered; resuming readings", messages)


if __name__ == "__main__":
    unittest.main()

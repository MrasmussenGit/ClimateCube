import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from services import mqtt_listener as listener


class ListenerLoggingTests(unittest.TestCase):
    def test_logging_writes_to_console_and_rotating_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"CLIMATECUBE_LOG_DIR": directory}):
                with patch("sys.stderr") as console:
                    listener.configure_logging()
                    try:
                        listener.LOGGER.warning("connection diagnostic")
                        handlers = listener.LOGGER.handlers
                        file_handler = next(
                            handler for handler in handlers
                            if isinstance(handler, RotatingFileHandler)
                        )
                        self.assertEqual(file_handler.maxBytes, 1024 * 1024)
                        self.assertEqual(file_handler.backupCount, 3)
                        log_file = Path(directory) / "mqtt_listener.log"
                        text = log_file.read_text(encoding="utf-8")
                        self.assertRegex(text, r"\d{4}-\d{2}-\d{2} .*WARNING")
                        self.assertIn("connection diagnostic", text)
                        self.assertTrue(console.write.called)
                        file_handler.doRollover()
                        listener.LOGGER.info("after rotation")
                        self.assertTrue(Path(str(log_file) + ".1").exists())
                        self.assertIn("after rotation", log_file.read_text())
                        self.assertNotIn("connection diagnostic", log_file.read_text())
                    finally:
                        for handler in listener.LOGGER.handlers[:]:
                            listener.LOGGER.removeHandler(handler)
                            handler.close()

    def test_unwritable_log_directory_fails_visibly(self):
        with tempfile.TemporaryDirectory() as directory:
            occupied = Path(directory) / "not-a-directory"
            occupied.write_text("occupied")
            with patch.dict(os.environ, {"CLIMATECUBE_LOG_DIR": str(occupied)}):
                with self.assertRaises(OSError):
                    listener.configure_logging()

    def test_connection_and_subscription_diagnostics(self):
        client = Mock()
        client.subscribe.return_value = (listener.mqtt.MQTT_ERR_SUCCESS, 7)
        with self.assertLogs(listener.LOGGER, level="INFO") as logs:
            listener.on_connect(client, None, {"session present": False}, 0)
            listener.on_subscribe(client, None, 7, (1,))
            listener.on_disconnect(client, None, 7)
        client.subscribe.assert_called_once_with(listener.MQTT_TOPIC, qos=1)
        text = "\n".join(logs.output)
        self.assertIn("subscription requested", text)
        self.assertIn("Listening for ClimateCube messages", text)
        self.assertIn("connection lost: code=7", text)

    def test_rejected_connection_does_not_subscribe(self):
        client = Mock()
        with self.assertLogs(listener.LOGGER, level="ERROR") as logs:
            listener.on_connect(client, None, {}, 5)
        client.subscribe.assert_not_called()
        self.assertIn("connection rejected: code=5", logs.output[0])

    def test_subscription_failures_are_logged(self):
        client = Mock()
        client.subscribe.return_value = (listener.mqtt.MQTT_ERR_NO_CONN, None)
        with self.assertLogs(listener.LOGGER, level="ERROR") as logs:
            listener.on_connect(client, None, {}, 0)
            listener.on_subscribe(client, None, 7, (128,))
        self.assertIn("subscribe request failed", logs.output[0])
        self.assertIn("subscription rejected", logs.output[1])

    def test_message_failures_do_not_stop_callback(self):
        message = SimpleNamespace(
            topic=listener.MQTT_TOPIC, payload=b"invalid", qos=1
        )
        errors = (
            (ValueError("invalid input"), "Invalid MQTT message", False),
            (sqlite3.OperationalError("disk full"), "Database error", True),
            (RuntimeError("unexpected"), "Unexpected MQTT message error", True)
        )
        for error, expected, traceback_expected in errors:
            with self.subTest(error=error):
                with patch.object(listener, "on_message", side_effect=error):
                    with self.assertLogs(listener.LOGGER, level="WARNING") as logs:
                        listener.safe_on_message(None, None, message)
                self.assertIn(expected, logs.output[0])
                self.assertEqual(
                    "Traceback" in logs.output[0], traceback_expected
                )

    def test_startup_failure_is_logged_and_reraised(self):
        with patch.object(listener, "configure_logging"):
            with patch.object(listener, "ensure_schema",
                              side_effect=sqlite3.OperationalError("disk full")):
                with self.assertLogs(listener.LOGGER, level="ERROR") as logs:
                    with self.assertRaises(sqlite3.OperationalError):
                        listener.main()
        self.assertIn("MQTT listener failed", logs.output[0])
        self.assertIn("Traceback", logs.output[0])

    def test_main_wires_diagnostics_and_preserves_broker(self):
        client = Mock()
        with patch.object(listener, "configure_logging"):
            with patch.object(listener, "ensure_schema"):
                with patch.object(listener.mqtt, "Client", return_value=client):
                    listener.main()
        client.enable_logger.assert_called_once()
        self.assertIs(client.on_connect, listener.on_connect)
        self.assertIs(client.on_disconnect, listener.on_disconnect)
        self.assertIs(client.on_subscribe, listener.on_subscribe)
        self.assertIs(client.on_message, listener.safe_on_message)
        client.connect.assert_called_once_with("localhost", 1883)
        client.loop_forever.assert_called_once()

    def test_valid_reading_is_stored_without_logging_full_payload(self):
        payload = {
            "device_id": "CC-test",
            "timestamp": "2026-11-26T21:00:00",
            "temperature_c": 21.5,
            "humidity_pct": 45,
            "pressure_hpa": 1013,
            "private_extra": "not-for-logs",
            "measurements": [{
                "key": "temperature_c", "label": "Temperature",
                "unit": "C", "value": 21.5
            }]
        }
        message = SimpleNamespace(
            topic=listener.MQTT_TOPIC,
            payload=json.dumps(payload).encode(),
            qos=1
        )
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "readings.db"
            schema = Path(__file__).resolve().parents[1] / "db" / "create_database.sql"
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript(schema.read_text())
            with patch.object(listener, "DB_FILE", str(database)):
                with self.assertLogs(listener.LOGGER, level="INFO") as logs:
                    listener.safe_on_message(None, None, message)
            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    "SELECT temperature_c, humidity_pct, pressure_hpa "
                    "FROM sensor_reading"
                ).fetchone()
                count = connection.execute(
                    "SELECT COUNT(*) FROM sensor_measurement"
                ).fetchone()[0]
            self.assertEqual(row, (21.5, 45, 1013))
            self.assertEqual(count, 1)
        text = "\n".join(logs.output)
        self.assertIn("Reading stored: device_id=CC-test", text)
        self.assertNotIn("not-for-logs", text)


if __name__ == "__main__":
    unittest.main()

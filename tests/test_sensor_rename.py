import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from services import database, web_server


class SensorRenameTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db_file = Path(self.directory.name) / "test.db"
        with closing(sqlite3.connect(self.db_file)) as conn, conn:
            conn.execute(
                "CREATE TABLE sensor (sensor_id INTEGER PRIMARY KEY, sensor_name TEXT)"
            )
            conn.execute("INSERT INTO sensor VALUES (1, 'Original')")
        patcher = patch.object(database, "get_connection", self.get_connection)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = web_server.app.test_client()
        self.url = "/settings/sensor/1/name"
        self.headers = {"Accept": "application/json"}

    def get_connection(self):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        return conn

    def stored_name(self):
        with closing(sqlite3.connect(self.db_file)) as conn:
            return conn.execute(
                "SELECT sensor_name FROM sensor WHERE sensor_id = 1"
            ).fetchone()[0]

    def test_inline_rename_persists_trimmed_name(self):
        response = self.client.post(
            self.url, data={"sensor_name": "  Kitchen <Cube>  "},
            headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {
            "sensor_id": 1, "sensor_name": "Kitchen <Cube>"
        })
        self.assertEqual(self.stored_name(), "Kitchen <Cube>")

    def test_invalid_names_leave_original_unchanged(self):
        for name in ("", "   ", "x" * 51):
            with self.subTest(name=name):
                response = self.client.post(
                    self.url, data={"sensor_name": name}, headers=self.headers
                )
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.json["error"])
                self.assertEqual(self.stored_name(), "Original")
        response = self.client.post(
            self.url, data={"sensor_name": "x" * 50}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stored_name(), "x" * 50)

    def test_missing_sensor_returns_json_error(self):
        response = self.client.post(
            "/settings/sensor/999/name", data={"sensor_name": "Kitchen"},
            headers=self.headers
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json, {"error": "Sensor not found."})

    def test_settings_form_keeps_redirects(self):
        response = self.client.post(self.url, data={"sensor_name": "Kitchen"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/settings?saved=1")
        self.assertEqual(self.stored_name(), "Kitchen")
        response = self.client.post(self.url, data={"sensor_name": " "})
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=Sensor+name+cannot+be+empty.", response.location)
        self.assertEqual(self.stored_name(), "Kitchen")


if __name__ == "__main__":
    unittest.main()

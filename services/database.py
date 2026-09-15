import json
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = PROJECT_DIR / "data" / "climatecube.db"

HISTORY_RANGES = {
    "6h": ("-6 hours", 60),
    "24h": ("-24 hours", 300),
    "3d": ("-3 days", 900),
    "7d": ("-7 days", 1800)
}


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_weather_schema():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS weather_observation (
                observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                observed_ts DATETIME NOT NULL,
                insert_ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                provider TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                temperature_c REAL NOT NULL,
                humidity_pct REAL NOT NULL,
                dew_point_c REAL,
                pressure_hpa REAL,
                precipitation_mm REAL,
                wind_speed_kmh REAL,
                cloud_cover_pct REAL,
                weather_code INTEGER,
                UNIQUE(provider, observed_ts, latitude, longitude)
            );
            CREATE INDEX IF NOT EXISTS idx_weather_observation_time
            ON weather_observation(observed_ts);
            CREATE TABLE IF NOT EXISTS app_setting (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL
            );
            """
        )


def get_weather_settings():
    ensure_weather_schema()

    with get_connection() as conn:
        settings = {
            row["setting_key"]: row["setting_value"]
            for row in conn.execute(
                """
                SELECT setting_key, setting_value
                FROM app_setting
                WHERE setting_key LIKE 'weather_%'
                """
            )
        }

    return {
        "latitude": settings.get("weather_latitude", ""),
        "longitude": settings.get("weather_longitude", ""),
        "zip_code": settings.get("weather_zip_code", ""),
        "place_name": settings.get("weather_place_name", ""),
        "state": settings.get("weather_state", ""),
        "location_name": settings.get(
            "weather_location_name",
            "Outdoor Weather"
        )
    }


def update_weather_settings(
    latitude,
    longitude,
    location_name,
    zip_code="",
    place_name="",
    state=""
):
    ensure_weather_schema()
    values = {
        "weather_latitude": str(latitude),
        "weather_longitude": str(longitude),
        "weather_location_name": location_name,
        "weather_zip_code": zip_code,
        "weather_place_name": place_name,
        "weather_state": state
    }

    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO app_setting (setting_key, setting_value)
            VALUES (?, ?)
            ON CONFLICT(setting_key)
            DO UPDATE SET setting_value = excluded.setting_value
            """,
            values.items()
        )


def get_latest_weather():
    ensure_weather_schema()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM weather_observation
            ORDER BY observed_ts DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return None

    weather = dict(row)
    weather["location_name"] = get_weather_settings()["location_name"]
    return weather


def get_latest_readings(include_inactive=False):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.sensor_id,
                s.sensor_name,
                s.device_id,
                s.ip_address,
                s.active_flag,
                s.reading_interval_sec,
                s.hardware_json,
                r.pico_ts AS reading_time,
                r.insert_ts AS last_contact_time,
                r.temperature_c,
                r.humidity_pct,
                r.pressure_hpa,
                r.gas_resistance_ohms
            FROM sensor_reading AS r
            JOIN sensor AS s
                ON s.sensor_id = r.sensor_id
            WHERE r.reading_id IN
            (
                SELECT MAX(reading_id)
                FROM sensor_reading
                GROUP BY sensor_id
            )
              AND (? = 1 OR s.active_flag = 1)
            ORDER BY s.sensor_name
            """,
            (1 if include_inactive else 0,)
        ).fetchall()

    readings = []

    for row in rows:
        reading = dict(row)
        hardware_json = reading.pop("hardware_json", None)

        try:
            reading["hardware"] = json.loads(hardware_json) if hardware_json else None
        except (TypeError, json.JSONDecodeError):
            reading["hardware"] = None

        readings.append(reading)

    return readings


def get_sensor(sensor_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT sensor_id, sensor_name, device_id, ip_address
            FROM sensor
            WHERE sensor_id = ?
            """,
            (sensor_id,)
        ).fetchone()

    return dict(row) if row else None


def get_sensors():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.sensor_id,
                s.sensor_name,
                s.device_id,
                s.ip_address,
                s.active_flag,
                MAX(COALESCE(r.pico_ts, r.insert_ts)) AS last_reading_time
            FROM sensor AS s
            LEFT JOIN sensor_reading AS r
                ON r.sensor_id = s.sensor_id
            GROUP BY
                s.sensor_id,
                s.sensor_name,
                s.device_id,
                s.ip_address,
                s.active_flag
            ORDER BY s.sensor_name
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_hidden_sensor_count():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM sensor WHERE active_flag = 0"
        ).fetchone()

    return row["count"]


def update_sensor_name(sensor_id, sensor_name):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE sensor
            SET sensor_name = ?
            WHERE sensor_id = ?
            """,
            (sensor_name, sensor_id)
        )

    return cursor.rowcount == 1


def update_sensor_visibility(sensor_id, is_visible):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE sensor
            SET active_flag = ?
            WHERE sensor_id = ?
            """,
            (1 if is_visible else 0, sensor_id)
        )

    return cursor.rowcount == 1


def get_temperature_history(sensor_id, range_name):
    modifier, bucket_seconds = HISTORY_RANGES[range_name]

    with get_connection() as conn:
        rows = conn.execute(
            """
            WITH latest AS
            (
                SELECT MAX(COALESCE(pico_ts, insert_ts)) AS latest_ts
                FROM sensor_reading
                WHERE sensor_id = ?
            )
            SELECT
                MAX(COALESCE(r.pico_ts, r.insert_ts)) AS reading_time,
                AVG(r.temperature_c) AS temperature_c,
                AVG(r.humidity_pct) AS humidity_pct,
                AVG(r.pressure_hpa) AS pressure_hpa,
                AVG(r.gas_resistance_ohms) AS gas_resistance_ohms
            FROM sensor_reading AS r
            CROSS JOIN latest
            WHERE r.sensor_id = ?
              AND datetime(
                    replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                  ) >= datetime(
                    replace(latest.latest_ts, 'T', ' '), ?
                  )
            GROUP BY
                CAST(
                    strftime(
                        '%s',
                        replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                    ) AS INTEGER
                ) / ?
            ORDER BY reading_time
            """,
            (sensor_id, sensor_id, modifier, bucket_seconds)
        ).fetchall()

    return [dict(row) for row in rows]


def add_outdoor_comparison(readings):
    if not readings:
        return readings

    ensure_weather_schema()
    reading_times = [
        datetime.fromisoformat(reading["reading_time"].replace("T", " "))
        for reading in readings
    ]

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT observed_ts, temperature_c, humidity_pct, dew_point_c
            FROM weather_observation
            WHERE datetime(observed_ts) BETWEEN datetime(?, '-30 minutes')
                                           AND datetime(?, '+30 minutes')
            ORDER BY observed_ts
            """,
            (readings[0]["reading_time"], readings[-1]["reading_time"])
        ).fetchall()

    weather = [dict(row) for row in rows]

    for reading, reading_time in zip(readings, reading_times):
        nearest = min(
            weather,
            key=lambda item: abs(
                datetime.fromisoformat(item["observed_ts"]) - reading_time
            ),
            default=None
        )

        if nearest is None or abs(
            datetime.fromisoformat(nearest["observed_ts"]) - reading_time
        ).total_seconds() > 1800:
            reading["outdoor_temperature_c"] = None
            reading["outdoor_humidity_pct"] = None
            reading["outdoor_dew_point_c"] = None
            continue

        reading["outdoor_temperature_c"] = nearest["temperature_c"]
        reading["outdoor_humidity_pct"] = nearest["humidity_pct"]
        reading["outdoor_dew_point_c"] = nearest["dew_point_c"]

    return readings

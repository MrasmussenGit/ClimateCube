import sqlite3
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


def get_latest_readings():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.sensor_id,
                s.sensor_name,
                s.device_id,
                s.ip_address,
                r.pico_ts AS reading_time,
                r.temperature_c,
                r.humidity_pct,
                r.pressure_hpa
            FROM sensor_reading AS r
            JOIN sensor AS s
                ON s.sensor_id = r.sensor_id
            WHERE r.reading_id IN
            (
                SELECT MAX(reading_id)
                FROM sensor_reading
                GROUP BY sensor_id
            )
            ORDER BY s.sensor_name
            """
        ).fetchall()

    return [dict(row) for row in rows]


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
                MAX(COALESCE(r.pico_ts, r.insert_ts)) AS last_reading_time
            FROM sensor AS s
            LEFT JOIN sensor_reading AS r
                ON r.sensor_id = s.sensor_id
            GROUP BY
                s.sensor_id,
                s.sensor_name,
                s.device_id,
                s.ip_address
            ORDER BY s.sensor_name
            """
        ).fetchall()

    return [dict(row) for row in rows]


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
                AVG(r.pressure_hpa) AS pressure_hpa
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

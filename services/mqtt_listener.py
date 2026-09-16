import json
import math
import re
import sqlite3

from paho.mqtt import client as mqtt

DB_FILE = "data/climatecube.db"
MQTT_TOPIC = "climatecube/readings"
MEASUREMENT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
DISPLAY_FORMATS = {"number", "resistance", "temperature"}


def on_connect(client, userdata, flags, reason_code):
    if reason_code != 0:
        print(f"MQTT connection failed with code {reason_code}", flush=True)
        return

    client.subscribe(MQTT_TOPIC, qos=1)
    print(f"Listening for ClimateCube messages on {MQTT_TOPIC}...", flush=True)


def on_disconnect(client, userdata, reason_code):
    if reason_code != 0:
        print("MQTT connection lost; reconnecting...", flush=True)


def ensure_schema():
    with sqlite3.connect(DB_FILE) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS measurement_definition (
                measurement_key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                unit TEXT NOT NULL,
                precision_digits INTEGER NOT NULL DEFAULT 2,
                display_format TEXT NOT NULL DEFAULT 'number',
                display_order INTEGER NOT NULL DEFAULT 100
            );
            CREATE TABLE IF NOT EXISTS sensor_measurement (
                reading_id INTEGER NOT NULL,
                measurement_key TEXT NOT NULL,
                measurement_value REAL NOT NULL,
                PRIMARY KEY (reading_id, measurement_key),
                FOREIGN KEY (reading_id)
                    REFERENCES sensor_reading(reading_id) ON DELETE CASCADE,
                FOREIGN KEY (measurement_key)
                    REFERENCES measurement_definition(measurement_key)
            );
            CREATE INDEX IF NOT EXISTS idx_sensor_measurement_key_reading
            ON sensor_measurement(measurement_key, reading_id);
            """
        )

        sensor_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(sensor)")
        }

        if "reading_interval_sec" not in sensor_columns:
            conn.execute(
                "ALTER TABLE sensor "
                "ADD COLUMN reading_interval_sec INTEGER"
            )

        if "hardware_json" not in sensor_columns:
            conn.execute(
                "ALTER TABLE sensor "
                "ADD COLUMN hardware_json TEXT"
            )

        reading_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(sensor_reading)")
        }

        if "insert_ts" not in reading_columns:
            conn.execute(
                "ALTER TABLE sensor_reading "
                "ADD COLUMN insert_ts DATETIME"
            )

            if "reading_ts" in reading_columns:
                conn.execute(
                    "UPDATE sensor_reading "
                    "SET insert_ts = reading_ts "
                    "WHERE insert_ts IS NULL"
                )
            else:
                conn.execute(
                    "UPDATE sensor_reading "
                    "SET insert_ts = CURRENT_TIMESTAMP "
                    "WHERE insert_ts IS NULL"
                )

        if "gas_resistance_ohms" not in reading_columns:
            conn.execute(
                "ALTER TABLE sensor_reading "
                "ADD COLUMN gas_resistance_ohms INTEGER"
            )


def get_hardware_metadata(payload):
    hardware_devices = payload.get("hardware_devices")

    if isinstance(hardware_devices, list):
        normalized_hardware = []
        for device in hardware_devices:
            if not isinstance(device, str):
                continue
            device = device.strip()[:50]
            if device and device not in normalized_hardware:
                normalized_hardware.append(device)

        sensor_type = next(
            (device for device in normalized_hardware if device.startswith("BME")),
            None
        )
        return json.dumps(normalized_hardware), sensor_type

    hardware = payload.get("hardware")

    if isinstance(hardware, dict):
        hardware_names = {
            "bme280": "BME280",
            "bme688": "BME688",
            "mics6814": "MICS6814",
            "oled": "OLED"
        }
        normalized_hardware = [
            name for key, name in hardware_names.items() if hardware.get(key)
        ]

        if hardware.get("bme688"):
            sensor_type = "BME688"
        elif hardware.get("bme280"):
            sensor_type = "BME280"
        else:
            sensor_type = None

        return json.dumps(normalized_hardware), sensor_type

    if payload.get("gas_resistance_ohms") is not None:
        return None, "BME688"

    return None, None


def get_measurements(payload):
    descriptors = payload.get("measurements")
    if not isinstance(descriptors, list):
        return []

    measurements = []
    for descriptor in descriptors[:50]:
        if not isinstance(descriptor, dict):
            continue

        key = descriptor.get("key")
        label = descriptor.get("label")
        unit = descriptor.get("unit", "")

        if not isinstance(key, str) or not MEASUREMENT_KEY_PATTERN.fullmatch(key):
            continue
        if not isinstance(label, str) or not label.strip():
            continue
        if not isinstance(unit, str):
            continue

        try:
            value = float(descriptor.get("value"))
            precision = max(0, min(6, int(descriptor.get("precision", 2))))
            display_order = int(descriptor.get("order", 100))
        except (TypeError, ValueError):
            continue

        if not math.isfinite(value):
            continue

        display_format = descriptor.get("format", "number")
        if display_format not in DISPLAY_FORMATS:
            display_format = "number"

        measurements.append({
            "key": key,
            "label": label.strip()[:80],
            "unit": unit.strip()[:20],
            "value": value,
            "precision": precision,
            "format": display_format,
            "order": display_order
        })

    return measurements


def store_measurements(conn, reading_id, measurements):
    for measurement in measurements:
        conn.execute(
            """
            INSERT INTO measurement_definition
            (
                measurement_key,
                label,
                unit,
                precision_digits,
                display_format,
                display_order
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(measurement_key) DO UPDATE SET
                label = excluded.label,
                unit = excluded.unit,
                precision_digits = excluded.precision_digits,
                display_format = excluded.display_format,
                display_order = excluded.display_order
            """,
            (
                measurement["key"],
                measurement["label"],
                measurement["unit"],
                measurement["precision"],
                measurement["format"],
                measurement["order"]
            )
        )
        conn.execute(
            """
            INSERT INTO sensor_measurement
            (reading_id, measurement_key, measurement_value)
            VALUES (?, ?, ?)
            """,
            (reading_id, measurement["key"], measurement["value"])
        )


def on_message(client, userdata, msg):

    print("MESSAGE RECEIVED")

    payload = json.loads(msg.payload.decode())

    print(f"Received: {payload}")

    ip_address = payload.get("ip_address")
    reading_interval_sec = payload.get("reading_interval_sec")
    hardware_json, sensor_type = get_hardware_metadata(payload)
    measurements = get_measurements(payload)

    if reading_interval_sec is not None:
        reading_interval_sec = int(reading_interval_sec)

        if reading_interval_sec <= 0:
            reading_interval_sec = None

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT sensor_id
        FROM sensor
        WHERE device_id = ?
        """,
        (payload["device_id"],)
    )

    row = cursor.fetchone()

    if row is None:

        print(
            f"Auto-registering device {payload['device_id']}"
        )

        display_name = (
            f"ClimateCube {payload['device_id'][-6:]}"
        )

        cursor.execute(
            """
            INSERT INTO sensor
            (
                device_id,
                sensor_name,
                sensor_type,
                install_date,
                ip_address,
                active_flag,
                reading_interval_sec,
                hardware_json
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
            """,
            (
                payload["device_id"],
                display_name,
                sensor_type or "Unknown",
                ip_address,
                1,
                reading_interval_sec,
                hardware_json
            )
        )

        conn.commit()

        sensor_id = cursor.lastrowid

        print(
            f"Registered as sensor_id {sensor_id}"
        )

    else:

        sensor_id = row[0]

        cursor.execute(
            """
            UPDATE sensor
            SET ip_address = COALESCE(?, ip_address),
                reading_interval_sec = COALESCE(?, reading_interval_sec),
                hardware_json = COALESCE(?, hardware_json),
                sensor_type = COALESCE(?, sensor_type)
            WHERE sensor_id = ?
            """,
            (
                ip_address,
                reading_interval_sec,
                hardware_json,
                sensor_type,
                sensor_id
            )
        )

    cursor.execute(
        """
        INSERT INTO sensor_reading
        (
            sensor_id,
            pico_ts,
            insert_ts,
            temperature_c,
            humidity_pct,
            pressure_hpa,
            gas_resistance_ohms
        )
        VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
        """,
        (
            sensor_id,
            payload["timestamp"],
            payload["temperature_c"],
            payload["humidity_pct"],
            payload["pressure_hpa"],
            payload.get("gas_resistance_ohms")
        )
    )

    store_measurements(conn, cursor.lastrowid, measurements)

    conn.commit()
    conn.close()

    print("Reading stored")


def safe_on_message(client, userdata, msg):
    try:
        on_message(client, userdata, msg)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"Invalid MQTT message ignored: {error}")
    except sqlite3.Error as error:
        print(f"Database error while processing MQTT message: {error}")
    except Exception as error:
        # An unexpected message must not terminate the MQTT network loop.
        print(f"Unexpected MQTT message error: {error}")


def main():
    ensure_schema()

    client = mqtt.Client()

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = safe_on_message

    client.connect("localhost", 1883)
    client.loop_forever()


if __name__ == "__main__":
    main()
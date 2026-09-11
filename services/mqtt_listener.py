import json
import sqlite3

from paho.mqtt import client as mqtt

DB_FILE = "data/climatecube.db"
MQTT_TOPIC = "climatecube/readings"


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
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(sensor)")
        }

        if "reading_interval_sec" not in columns:
            conn.execute(
                "ALTER TABLE sensor "
                "ADD COLUMN reading_interval_sec INTEGER"
            )

        if "hardware_json" not in columns:
            conn.execute(
                "ALTER TABLE sensor "
                "ADD COLUMN hardware_json TEXT"
            )


def on_message(client, userdata, msg):

    print("MESSAGE RECEIVED")

    payload = json.loads(msg.payload.decode())

    print(f"Received: {payload}")

    ip_address = payload.get("ip_address")
    reading_interval_sec = payload.get("reading_interval_sec")
    hardware = payload.get("hardware")
    hardware_json = None

    if isinstance(hardware, dict):
        hardware_json = json.dumps({
            "bme280": bool(hardware.get("bme280")),
            "oled": bool(hardware.get("oled"))
        })

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
                "BME280",
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
                hardware_json = COALESCE(?, hardware_json)
            WHERE sensor_id = ?
            """,
            (
                ip_address,
                reading_interval_sec,
                hardware_json,
                sensor_id
            )
        )

    cursor.execute(
        """
        INSERT INTO sensor_reading
        (
            sensor_id,
            pico_ts,
            temperature_c,
            humidity_pct,
            pressure_hpa
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            sensor_id,
            payload["timestamp"],
            payload["temperature_c"],
            payload["humidity_pct"],
            payload["pressure_hpa"]
        )
    )

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


ensure_schema()

client = mqtt.Client()

client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = safe_on_message

client.connect("localhost", 1883)

client.loop_forever()
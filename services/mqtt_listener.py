import json
import sqlite3

from paho.mqtt import client as mqtt

DB_FILE = "data/climatecube.db"


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


def on_message(client, userdata, msg):

    print("MESSAGE RECEIVED")

    payload = json.loads(msg.payload.decode())

    print(f"Received: {payload}")

    reading_interval_sec = payload.get("reading_interval_sec")

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
                reading_interval_sec
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            (
                payload["device_id"],
                display_name,
                "BME280",
                payload["ip_address"],
                1,
                reading_interval_sec
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
            SET ip_address = ?,
                reading_interval_sec = COALESCE(?, reading_interval_sec)
            WHERE sensor_id = ?
            """,
            (
                payload["ip_address"],
                reading_interval_sec,
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


ensure_schema()

client = mqtt.Client()

client.on_message = on_message

client.connect("localhost", 1883)

client.subscribe("climatecube/readings")

print("Listening for ClimateCube messages...")

client.loop_forever()
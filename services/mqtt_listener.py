import json
import sqlite3

from paho.mqtt import client as mqtt

DB_FILE = "data/climatecube.db"


def on_message(client, userdata, msg):

    print("MESSAGE RECEIVED")
    payload = json.loads(msg.payload.decode())

    print(f"Received: {payload}")

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
        print("Unknown device")
        conn.close()
        return

    sensor_id = row[0]

    cursor.execute(
        """
        INSERT INTO sensor_reading
        (
            sensor_id,
            reading_ts,
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


client = mqtt.Client()

client.on_message = on_message

client.connect("localhost", 1883)

client.subscribe("climatecube/readings")

print("Listening for ClimateCube messages...")

client.loop_forever()

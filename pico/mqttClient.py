from umqtt.simple import MQTTClient
import binascii
import json
import device
import os

from config import BROKER, READING_INTERVAL_SEC

DEVICE_ID = device.get_device_id()
MQTT_CLIENT_ID = "{}-{}".format(
    DEVICE_ID,
    binascii.hexlify(os.urandom(4)).decode()
)

TOPIC = "climatecube/readings"

client = None

def connect():
    global client

    client = MQTTClient(
        # A new ID per boot prevents a stale broker connection with the same
        # hardware ID from resetting a rapid reconnect after a Pico reboot.
        client_id=MQTT_CLIENT_ID,
        server=BROKER
    )

    client.connect()

def disconnect():
    global client

    if client is not None:
        try:
            client.disconnect()
        except Exception:
            pass

    client = None

def publish_reading(payload):

    if client is None:
        raise OSError("MQTT client is not connected")

    payload["device_id"] = DEVICE_ID
    payload["reading_interval_sec"] = READING_INTERVAL_SEC

    client.publish(
        TOPIC,
        json.dumps(payload),
        qos=1
    )

    print("Reading published")
    print(
        "Next reading in {} seconds".format(
            READING_INTERVAL_SEC
        )
    )
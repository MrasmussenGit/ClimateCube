from umqtt.simple import MQTTClient
import json
import device

from config import BROKER, READING_INTERVAL_SEC

DEVICE_ID = device.get_device_id()

TOPIC = "climatecube/readings"

client = None

def connect():
    global client

    client = MQTTClient(
        client_id=DEVICE_ID,
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
        json.dumps(payload)
    )

    print("Reading published")
    print(
        "Next reading in {} seconds".format(
            READING_INTERVAL_SEC
        )
    )
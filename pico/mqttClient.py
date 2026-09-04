from umqtt.simple import MQTTClient
import json
import device

from config import BROKER, READING_INTERVAL_SEC

DEVICE_ID = device.get_device_id()

TOPIC = "climatecube/readings"

client = MQTTClient(
    client_id=DEVICE_ID,
    server=BROKER
)

def connect():
    client.connect()

def publish_reading(payload):

    payload["device_id"] = DEVICE_ID

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
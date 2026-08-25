from umqtt.simple import MQTTClient
import json

BROKER = "192.168.1.36"

DEVICE_ID = "CC-0001"

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
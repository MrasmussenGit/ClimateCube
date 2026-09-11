from umqtt.simple import MQTTClient
import binascii
import json
import device
import os
import socket

from config import READING_INTERVAL_SEC
from defaults import BROKER

DEVICE_ID = device.get_device_id()
MQTT_CLIENT_ID = "{}-{}".format(
    DEVICE_ID,
    binascii.hexlify(os.urandom(4)).decode()
)

TOPIC = "climatecube/readings"

client = None

def connect():
    global client

    # MicroPython's MQTT client can reset the connection when given an mDNS
    # hostname even though socket resolution succeeds. Resolve it explicitly
    # and pass the IPv4 address to MQTTClient.
    broker_address = socket.getaddrinfo(BROKER, 1883)[0][-1][0]

    client = MQTTClient(
        # A new ID per boot prevents a stale broker connection with the same
        # hardware ID from resetting a rapid reconnect after a Pico reboot.
        client_id=MQTT_CLIENT_ID,
        server=broker_address
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
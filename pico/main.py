import wifi
import ntpTime
import sensor
import time
import mqttClient
import display
import device
from machine import RTC
from config import READING_INTERVAL_SEC

RECONNECT_DELAY_SEC = 10

def log(msg):
    print(msg)

    try:
        with open("boot.log", "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass

def get_ip_address(wlan):
    if wlan is None or not wlan.isconnected():
        return None

    ip_address = wlan.ifconfig()[0]

    if not ip_address or ip_address == "0.0.0.0":
        return None

    return ip_address


def ensure_wifi(wlan=None):
    while True:
        ip_address = get_ip_address(wlan)

        if ip_address is not None:
            return wlan, ip_address

        log("Connecting to WiFi")
        wlan = wifi.connect()
        ip_address = get_ip_address(wlan)

        if ip_address is not None:
            log("WiFi OK")
            log("IP Address: {}".format(ip_address))
            return wlan, ip_address

        log("WiFi unavailable; retrying in {} seconds".format(
            RECONNECT_DELAY_SEC
        ))
        time.sleep(RECONNECT_DELAY_SEC)


def ensure_mqtt(wlan):
    while True:
        wlan, ip_address = ensure_wifi(wlan)

        try:
            mqttClient.connect()
            log("Connected to message queue")
            return wlan, ip_address
        except Exception as e:
            log("MQTT connection failed: {}".format(e))
            mqttClient.disconnect()
            log("Retrying MQTT in {} seconds".format(
                RECONNECT_DELAY_SEC
            ))
            time.sleep(RECONNECT_DELAY_SEC)


# Connect to WiFi
log("Starting WiFi")
wlan, ip_address = ensure_wifi()

log("WiFi OK")
log("IP Address: {}".format(ip_address))

log("Syncing time")

if ntpTime.sync_time():
    log("Time synced")
else:
    log("Time sync failed")

log("Setting up display")
display.init()
log("Display initialized")

# Initialize RTC
log("Initializing RTC")
rtc = RTC()

# Connect MQTT
log("Connecting to message queue")
wlan, ip_address = ensure_mqtt(wlan)

log(
    "Device ID: {}".format(
        device.get_device_id()
    )
)

log("Monitor Started")
log("----------------------------")

while True:
    data = sensor.GetTempData()
    dt = rtc.datetime()
    display.update(data, dt)

    hour = dt[4]

    timestamp = "{}-{:02}-{:02}T{:02}:{:02}:{:02}".format(
        dt[0],  # year
        dt[1],  # month
        dt[2],  # day
        hour,
        dt[5],
        dt[6]
    )

    payload = {
        "device_id": "CC-0001",
        "ip_address": ip_address,
        "timestamp": timestamp,
        "temperature_c": data["temperature_c"],
        "humidity_pct": data["humidity_pct"],
        "pressure_hpa": data["pressure_hpa"]
    }

    log(timestamp)
    log(f"Temp = {data['temperature_c']} C")
    log(f"Humidity = {data['humidity_pct']} %")
    log(f"Pressure = {data['pressure_hpa']} hPa")
    log("")

    while True:
        wlan, ip_address = ensure_wifi(wlan)
        payload["ip_address"] = ip_address

        try:
            mqttClient.publish_reading(payload)
            break
        except Exception as e:
            log("MQTT publish failed: {}".format(e))
            mqttClient.disconnect()
            wlan, ip_address = ensure_mqtt(wlan)

    time.sleep(READING_INTERVAL_SEC)
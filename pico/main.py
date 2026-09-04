import wifi
import ntpTime
import sensor
import time
import mqttClient
import display
import device
from machine import RTC
from config import READING_INTERVAL_SEC

def log(msg):
    print(msg)

    try:
        with open("boot.log", "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass

# Connect to WiFi
log("Starting WiFi")
wlan = wifi.connect()

if wlan is None:
    log("WiFi Startup Failed")
    raise Exception("WiFi startup failed")
ip_address = wlan.ifconfig()[0]

if not wlan.isconnected() or not ip_address or ip_address == "0.0.0.0":
    log("No valid IP address")
    raise Exception("No valid IP address")

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

try:
    mqttClient.connect()
    log("Connected to message queue")
except Exception as e:
    log("MQTT connection failed: {}".format(e))
    raise

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
    mqttClient.publish_reading(payload)
    time.sleep(READING_INTERVAL_SEC)
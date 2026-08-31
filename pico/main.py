import wifi
import ntpTime
import sensor
import time
import mqttClient
import display
from machine import RTC

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

log("WiFi OK")

log("Setting up display")
display.init()
log("Display initialized")
# Sync time from NTP
log("Skipping NTP Sync")

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

log("Monitor Started")
log("----------------------------")

while True:
    data = sensor.GetTempData()

    dt = rtc.datetime()

    hour = (dt[4] - 4) % 24

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
    log("Reading published")
    time.sleep(10)
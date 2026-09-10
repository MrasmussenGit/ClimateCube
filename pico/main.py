import wifi
import ntpTime
import sensor
import time
import mqttClient
import display
import device
import os
from machine import RTC
from config import READING_INTERVAL_SEC

RECONNECT_DELAY_SEC = 10
SENSOR_RETRY_DELAYS_SEC = (10, 30, 60)
LOG_FILE = "boot.log"
OLD_LOG_FILE = "boot.log.old"
MAX_LOG_SIZE_BYTES = 16 * 1024


def rotate_log_if_needed():
    try:
        if os.stat(LOG_FILE)[6] < MAX_LOG_SIZE_BYTES:
            return
    except OSError:
        return

    try:
        os.remove(OLD_LOG_FILE)
    except OSError:
        pass

    try:
        os.rename(LOG_FILE, OLD_LOG_FILE)
    except OSError:
        # If rotation fails, remove the active log so logging cannot fill
        # the filesystem indefinitely.
        try:
            os.remove(LOG_FILE)
        except OSError:
            pass

def log(msg):
    print(msg)

    try:
        rotate_log_if_needed()

        with open(LOG_FILE, "a") as f:
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


def wait_for_next_reading(data):
    remaining = READING_INTERVAL_SEC

    while remaining > 0:
        display.update(data, rtc.datetime(), remaining)
        time.sleep(1)
        remaining -= 1


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
if display.init():
    log("Display initialized")
else:
    log("Display not detected; continuing without it")

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

sensor_missing = False
sensor_retry_index = 0

while True:
    data = sensor.GetTempData()

    if data is None:
        retry_delay = SENSOR_RETRY_DELAYS_SEC[sensor_retry_index]

        if not sensor_missing:
            log("BME280 sensor not detected")
            sensor_missing = True

        # Refresh the warning on every retry. This also initializes an OLED
        # that is connected after startup.
        display.show_sensor_not_detected()
        time.sleep(retry_delay)
        sensor_retry_index = min(
            sensor_retry_index + 1,
            len(SENSOR_RETRY_DELAYS_SEC) - 1
        )
        continue

    if sensor_missing:
        log("BME280 sensor detected; resuming readings")
        sensor_missing = False
        sensor_retry_index = 0

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
            display.show_publish_success()
            break
        except Exception as e:
            log("MQTT publish failed: {}".format(e))
            mqttClient.disconnect()
            wlan, ip_address = ensure_mqtt(wlan)

    wait_for_next_reading(data)
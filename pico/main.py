import wifi
import ntpTime
import sensor
import time
import mqttClient
from machine import RTC

# Connect to WiFi
wifi.connect()

# Sync time from NTP
ntpTime.sync_time()
rtc = RTC()
print("Connecting to message queue")
mqttClient.connect()
print("Connected to message queue")
print("Monitor Started")
print("----------------------")

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

    print(timestamp)
    print(f"Temp = {data['temperature_c']} C")
    print(f"Humidity = {data['humidity_pct']} %")
    print(f"Pressure = {data['pressure_hpa']} hPa")
    print()
    mqttClient.publish_reading(payload)
    time.sleep(10)
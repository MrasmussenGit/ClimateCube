# ClimateCube Project Status

Date: 2026-08-25

CURRENT STATUS
==============
Phase 1 Complete

Architecture:

BME280
  ->
Pico W
  ->
WiFi
  ->
MQTT Publish
  ->
Mosquitto
  ->
mqtt_listener.py
  ->
SQLite

WORKING
=======
- BME280 sensor readings
- WiFi connectivity
- NTP time sync
- MQTT connection
- MQTT publishing
- MQTT subscription
- Mosquitto broker
- SQLite database
- MQTT listener
- Database inserts

MQTT
====
Topic:
climatecube/readings

Payload:

{
  "device_id": "CC-0001",
  "timestamp": "2026-08-25T09:22:50",
  "temperature_c": 20.7,
  "humidity_pct": 62.76,
  "pressure_hpa": 1002.85
}

DATABASE
========
File:
data/climatecube.db

Tables:
- room
- sensor
- room_assignment
- sensor_reading

Design:
sensor_id = INTEGER PRIMARY KEY AUTOINCREMENT
device_id = unique device identifier

Current device:
CC-0001

MAJOR FIXES
===========
1. MQTT connect after WiFi connect
2. Main loop indentation fixed
3. Celsius standardized
4. Python venv activated
5. MQTT topic corrected:
   climatecube/device/# -> climatecube/readings
6. Payload names corrected:
   temperature -> temperature_c
   humidity -> humidity_pct
   pressure -> pressure_hpa

VERIFIED
========
SELECT COUNT(*) FROM sensor_reading;

Result:
5

Rows successfully inserted.

NEXT STEP
=========
Build reporting/query layer.

Examples:
- Latest readings
- Temperature history
- Daily averages
- Min/max values
- Room reports

Future:
Dashboard and charts
Multi-device support
Device onboarding

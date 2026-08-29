Copilot said:

ClimateCube Hub Imaging Guide

Prerequisites

Raspberry Pi OS Lite

During imaging:

Configure WiFi
Enable SSH

Verify Connectivity

SSH to the Pi:

ssh localadmin@

Verify Internet access:

ping github.com

Install Git

sudo apt update

sudo apt upgrade -y

sudo apt install -y git

Clone ClimateCube

git clone https://github.com/MrasmussenGit/ClimateCube.git

cd ClimateCube

Run Setup

chmod +x scripts/setup.sh

./scripts/setup.sh

Setup performs:

Install sqlite3
Install mosquitto
Install mosquitto-clients
Install python3-venv
Create Python virtual environment
Install Python packages
Configure Mosquitto listener
Create database
Create tables
Seed database

Verify Database

Verify tables:

sqlite3 data/climatecube.db ".tables"

Expected:

room
 room_assignment
 sensor
 sensor_reading

Verify sensor seed:

sqlite3 data/climatecube.db "SELECT * FROM sensor;"

Expected:

1|CC-0001|ClimateCube #1|BME280||1

Verify room seed:

sqlite3 data/climatecube.db "SELECT * FROM room;"

Expected:

1|Living Room|Main living area

Verify room assignment seed:

sqlite3 data/climatecube.db "SELECT * FROM room_assignment;"

Expected:

1|1|1|...

Verify Mosquitto

sudo ss -tlnp | grep 1883

Expected:

0.0.0.0:1883

Start ClimateCube Listener

source .venv/bin/activate

python services/mqtt_listener.py

Expected:

Listening for ClimateCube messages...

Verify MQTT Traffic

Open a second SSH session:

mosquitto_sub -h localhost -t climatecube/readings -v

Expected:

climatecube/readings {...}

Verify Database Inserts

sqlite3 data/climatecube.db

SELECT COUNT(*) FROM sensor_reading;

Expected:

Count increases as Pico readings arrive.

Known Issues

Pico WiFi Startup

Occasionally the Pico does not associate with WiFi on the first connection attempt.

Current behavior:

Pico boots
 ↓
 WiFi retry logic runs
 ↓
 Connection succeeds automatically

Boot diagnostics are written to:

boot.log

on the Pico.

NTP Synchronization

NTP synchronization is currently disabled until timeout and retry handling are improved.

Current recommendation:

Use insert_ts for trusted timestamps.

Store pico_ts from the sensor separately.

Recovery Validation Status

Validated:

✅ Fresh Raspberry Pi OS Lite

✅ Git clone from GitHub

✅ setup.sh execution

✅ Database creation

✅ Seed data creation

✅ Mosquitto configuration

✅ MQTT listener operation

✅ Pico reconnection

✅ Data insertion into SQLite

✅ Full rebuild from blank SD card

✅ Recovery from hub replacement scenario

Current Install Process

sudo apt update

sudo apt upgrade -y

sudo apt install -y git

git clone https://github.com/MrasmussenGit/ClimateCube.git

cd ClimateCube

chmod +x scripts/setup.sh

./scripts/setup.sh

source .venv/bin/activate

python services/mqtt_listener.py

Outcome:

Fresh Pi → Setup → MQTT Listener → Pico → SQLite Database ✅
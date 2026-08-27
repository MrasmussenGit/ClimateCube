OS Packages
-----------
git
sqlite3
mosquitto
mosquitto-clients
python3-venv


Python Packages
---------------
paho-mqtt
mpremote
pyserial
bme280
smbus2
platformdirs


Steps
-----
Install Raspberry Pi OS Lite

Enable SSH - during imaging

sudo apt update

sudo apt upgrade -y

sudo apt install -y git

sudo apt install -y sqlite3

sudo apt install -y mosquitto mosquitto-clients

sudo apt install -y python3-venv

git clone https://github.com/MrasmussenGit/ClimateCube.git

cd ClimateCube

python3 -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

Configure Mosquitto for network clients

sudo tee /etc/mosquitto/conf.d/climatecube.conf > /dev/null <<EOF
listener 1883
allow_anonymous true
EOF

sudo systemctl restart mosquitto

Verify Mosquitto Configuration

sudo ss -tlnp | grep 1883

Expected:
0.0.0.0:1883

Create data folder

mkdir -p data

Initialize database

bash scripts/init_db.sh

Verify database exists

ls data

Expected:
climatecube.db

Verify tables exist

sqlite3 data/climatecube.db ".tables"

Expected:
room
room_assignment
sensor
sensor_reading

(Optional Recovery Scenario)
Move replacement Pi to production IP

sudo nmcli connection modify netplan-wlan0-RangerTown \
ipv4.addresses 192.168.1.36/24 \
ipv4.gateway 192.168.1.1 \
ipv4.dns "8.8.8.8 1.1.1.1" \
ipv4.method manual

sudo reboot

Verify IP

hostname -I

Expected:
192.168.1.36

Start MQTT listener

source .venv/bin/activate

python services/mqtt_listener.py

Verify MQTT traffic

Open second terminal

mosquitto_sub -h localhost -t climatecube/readings -v

Expected:
climatecube/readings {...}

Verify database inserts

sqlite3 data/climatecube.db

SELECT COUNT(*) FROM sensor_reading;

Expected:
Count increases as Pico readings arrive.
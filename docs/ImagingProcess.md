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
---------------
1. Install Raspberry Pi OS Lite
2. Enable SSH
3. sudo apt update
4. sudo apt upgrade -y
5. sudo apt install -y git
6. sudo apt install -y sqlite3
7. sudo apt install -y mosquitto mosquitto-clients
8. sudo apt install -y python3-venv
9. git clone https://github.com/MrasmussenGit/ClimateCube.git
10. cd ClimateCube
11. python3 -m venv .venv
12. source .venv/bin/activate
13. pip install -r requirements.txt
14. bash scripts/init_db.sh
15. Verify database exists
16. Verify tables exist
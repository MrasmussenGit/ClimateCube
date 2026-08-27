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
sudo tee /etc/mosquitto/conf.d/climatecube.conf > /dev/null <<EOF
listener 1883
allow_anonymous true
EOF
bash scripts/init_db.sh
Verify database exists
Verify tables exist
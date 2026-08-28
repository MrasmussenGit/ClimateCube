#!/bin/bash

set -e

echo
echo "===================================="
echo "ClimateCube Setup"
echo "===================================="

echo
echo "Installing OS packages..."

sudo apt update

sudo apt install -y \
    git \
    sqlite3 \
    mosquitto \
    mosquitto-clients \
    python3-venv

echo
echo "Configuring Mosquitto..."

sudo tee /etc/mosquitto/conf.d/climatecube.conf > /dev/null <<EOF
listener 1883
allow_anonymous true
EOF

sudo systemctl enable mosquitto
sudo systemctl restart mosquitto

echo
echo "Creating Python virtual environment..."

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

echo
echo "Installing Python dependencies..."

source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

echo
echo "Initializing database..."

bash scripts/init_db.sh
if [ ! -f data/climatecube.db ]; then
    echo "ERROR: Database was not created"
    exit 1
fi

echo
echo "Verification"

echo
echo "SQLite Version:"
sqlite3 --version

echo
echo "Mosquitto Listener:"
sudo ss -tlnp | grep 1883 || {
    echo "ERROR: Mosquitto not listening on port 1883"
    exit 1
}

echo
echo "Database Tables:"
TABLES=$(sqlite3 data/climatecube.db ".tables")
echo "$TABLES"

echo
echo "===================================="
echo "ClimateCube Setup Complete"
echo "===================================="

echo
echo "To start the listener:"
echo
echo "source .venv/bin/activate"
echo "python services/mqtt_listener.py"
echo
echo "Validation Commands:"
echo
echo "python services/mqtt_listener.py"
echo
echo "Open another terminal:"
echo "mosquitto_sub -h localhost -t climatecube/readings -v"
echo
echo
echo "Verify Seed Data:"
echo
echo 'sqlite3 data/climatecube.db "SELECT * FROM sensor;"'
echo
echo 'sqlite3 data/climatecube.db "SELECT * FROM room;"'
echo
echo 'sqlite3 data/climatecube.db "SELECT * FROM room_assignment;"'
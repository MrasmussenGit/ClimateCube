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

python3 -m venv .venv

echo
echo "Installing Python dependencies..."

source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

echo
echo "Initializing database..."

bash scripts/init_db.sh

echo
echo "Verification"

echo
echo "SQLite Version:"
sqlite3 --version

echo
echo "Mosquitto Listener:"
sudo ss -tlnp | grep 1883

echo
echo "Database Tables:"
sqlite3 data/climatecube.db ".tables"

echo
echo "===================================="
echo "ClimateCube Setup Complete"
echo "===================================="

echo
echo "To start the listener:"
echo
echo "source .venv/bin/activate"
echo "python services/mqtt_listener.py"
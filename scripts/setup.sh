#!/bin/bash

set -e

echo
echo "===================================="
echo "ClimateCube Setup"
echo "===================================="

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${SUDO_USER:-$(id -un)}"

# Create config.py if missing
if [ ! -f pico/config.py ]; then
    echo ""
    echo "Creating pico/config.py from template..."
    cp pico/config_template.py pico/config.py

    echo ""
    echo "IMPORTANT:"
    echo "Edit pico/config.py and populate:"
    echo "  SSID"
    echo "  PASSWORD"
    echo "  BROKER"
    echo "  READING_INTERVAL_SEC"
    echo ""
fi

# Create firmware folder if missing
if [ ! -d firmware ]; then

    echo ""
    echo "Creating firmware directory..."
    mkdir firmware

fi

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
echo "Configuring ClimateCube MQTT listener..."

sudo tee /etc/systemd/system/climatecube-listener.service > /dev/null <<EOF
[Unit]
Description=ClimateCube MQTT Listener
After=network-online.target mosquitto.service
Wants=network-online.target
Requires=mosquitto.service

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$PROJECT_DIR/.venv/bin/python services/mqtt_listener.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable climatecube-listener
sudo systemctl restart climatecube-listener

echo
echo "ClimateCube MQTT Listener:"
sudo systemctl is-active --quiet climatecube-listener || {
    echo "ERROR: ClimateCube MQTT listener failed to start"
    sudo systemctl status climatecube-listener --no-pager
    exit 1
}

echo
echo "Configuring ClimateCube web server..."

sudo tee /etc/systemd/system/climatecube-web.service > /dev/null <<EOF
[Unit]
Description=ClimateCube Flask Web Server
After=network-online.target mosquitto.service
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/gunicorn \
    --workers 1 \
    --worker-class gthread \
    --threads 4 \
    --timeout 60 \
    --bind 0.0.0.0:5000 \
    services.web_server:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable climatecube-web
sudo systemctl restart climatecube-web

echo
echo "ClimateCube Web Server:"
sudo systemctl is-active --quiet climatecube-web || {
    echo "ERROR: ClimateCube web server failed to start"
    sudo systemctl status climatecube-web --no-pager
    exit 1
}

echo "Web server running on port 5000"

echo
echo "Service Status:"
echo "Mosquitto:     $(systemctl is-active mosquitto)"
echo "MQTT Listener: $(systemctl is-active climatecube-listener)"
echo "Web Server:    $(systemctl is-active climatecube-web)"

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
echo "Sensor:"
sqlite3 data/climatecube.db "SELECT * FROM sensor;"

echo
echo "Room:"
sqlite3 data/climatecube.db "SELECT * FROM room;"

echo
echo "Room Assignment:"
sqlite3 data/climatecube.db "SELECT * FROM room_assignment;"
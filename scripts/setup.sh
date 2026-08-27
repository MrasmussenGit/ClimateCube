sudo apt update

sudo apt install -y \
    git \
    sqlite3 \
    mosquitto \
    mosquitto-clients \
    python3-venv

python3 -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

mkdir -p data

sudo tee /etc/mosquitto/conf.d/climatecube.conf > /dev/null <<EOF
listener 1883
allow_anonymous true
EOF

sudo systemctl restart mosquitto

bash scripts/init_db.sh
#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PICO_DIR="$PROJECT_DIR/pico"
CONFIG_FILE=""
TEMP_CONFIG_FILE=""
PORT="auto"
BROKER_HOST="climatecube.local"

cleanup() {
    if [[ -n "$TEMP_CONFIG_FILE" && -f "$TEMP_CONFIG_FILE" ]]; then
        if command -v shred > /dev/null 2>&1; then
            shred -u "$TEMP_CONFIG_FILE"
        else
            rm -f "$TEMP_CONFIG_FILE"
        fi
    fi
}

trap cleanup EXIT HUP INT TERM

usage() {
    cat <<'EOF'
Usage: scripts/image_pico.sh [options]

Provision a Pico W that is already running MicroPython.

Options:
  --config FILE   Configuration file to install as config.py
                                    (default: securely prompt without saving locally)
  --port DEVICE   Serial device, such as /dev/ttyACM0 (default: auto)
  -h, --help      Show this help

Before running, flash the Pico W MicroPython UF2 if this is a fresh board.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)
            [[ $# -ge 2 ]] || { echo "ERROR: --config requires a file" >&2; exit 2; }
            CONFIG_FILE="$2"
            shift 2
            ;;
        --port)
            [[ $# -ge 2 ]] || { echo "ERROR: --port requires a device" >&2; exit 2; }
            PORT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if ! command -v mpremote > /dev/null 2>&1; then
    if [[ -x "$PROJECT_DIR/.venv/bin/mpremote" ]]; then
        MPREMOTE="$PROJECT_DIR/.venv/bin/mpremote"
    else
        echo "ERROR: mpremote is not installed." >&2
        echo "Run scripts/setup.sh or install it with: python3 -m pip install mpremote" >&2
        exit 1
    fi
else
    MPREMOTE="$(command -v mpremote)"
fi

BROKER="$(getent ahostsv4 "$BROKER_HOST" | awk 'NR == 1 { print $1 }')"

if [[ -z "$BROKER" ]]; then
    echo "ERROR: Cannot find the ClimateCube server at $BROKER_HOST." >&2
    echo "Confirm the server is running and connected to this network." >&2
    exit 1
fi

echo "ClimateCube server found at $BROKER"

if [[ -z "$CONFIG_FILE" ]]; then
    echo
    echo "Enter this Pico's settings. The password will not be displayed or saved."
    read -r -p "Wi-Fi name (SSID): " SSID
    read -r -s -p "Wi-Fi password: " PASSWORD
    echo
    read -r -p "Reading interval in seconds [600]: " READING_INTERVAL_SEC
    READING_INTERVAL_SEC="${READING_INTERVAL_SEC:-600}"

    if [[ -z "$SSID" || -z "$PASSWORD" ]]; then
        echo "ERROR: SSID and password are required." >&2
        exit 1
    fi

    if ! [[ "$READING_INTERVAL_SEC" =~ ^[1-9][0-9]*$ ]]; then
        echo "ERROR: Reading interval must be a positive whole number." >&2
        exit 1
    fi

    escape_python_string() {
        local value="$1"
        value="${value//\\/\\\\}"
        value="${value//\"/\\\"}"
        printf '%s' "$value"
    }

    TEMP_CONFIG_FILE="$(mktemp)"
    chmod 600 "$TEMP_CONFIG_FILE"
    {
        printf 'SSID = "%s"\n' "$(escape_python_string "$SSID")"
        printf 'PASSWORD = "%s"\n' "$(escape_python_string "$PASSWORD")"
        printf 'BROKER = "%s"\n' "$BROKER"
        printf 'READING_INTERVAL_SEC = %s\n' "$READING_INTERVAL_SEC"
    } > "$TEMP_CONFIG_FILE"
    CONFIG_FILE="$TEMP_CONFIG_FILE"
elif [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: Configuration file not found: $CONFIG_FILE" >&2
    exit 1
fi

if [[ "$CONFIG_FILE" != "$TEMP_CONFIG_FILE" ]]; then
    SOURCE_CONFIG_FILE="$CONFIG_FILE"
    TEMP_CONFIG_FILE="$(mktemp)"
    chmod 600 "$TEMP_CONFIG_FILE"
    grep -Ev '^BROKER[[:space:]]*=' "$SOURCE_CONFIG_FILE" > "$TEMP_CONFIG_FILE"
    printf 'BROKER = "%s"\n' "$BROKER" >> "$TEMP_CONFIG_FILE"
    CONFIG_FILE="$TEMP_CONFIG_FILE"
fi

for setting in SSID PASSWORD BROKER READING_INTERVAL_SEC; do
    if ! grep -Eq "^${setting}[[:space:]]*=[[:space:]]*[^[:space:]].*" "$CONFIG_FILE"; then
        echo "ERROR: $setting is missing from $CONFIG_FILE" >&2
        exit 1
    fi
done

if grep -Eq "^(SSID|PASSWORD)[[:space:]]*=[[:space:]]*(\"\"|'')[[:space:]]*$" "$CONFIG_FILE"; then
    echo "ERROR: SSID and PASSWORD must be populated in $CONFIG_FILE" >&2
    exit 1
fi

CONNECT=(connect "$PORT")

echo
echo "===================================="
echo "ClimateCube Pico W Imaging"
echo "===================================="
echo
echo "Checking connected board..."

BOARD="$($MPREMOTE "${CONNECT[@]}" exec "import os; print(os.uname().machine)")"
echo "Detected: $BOARD"

if [[ "$BOARD" != *"Pico W"* ]]; then
    echo "ERROR: Expected a Raspberry Pi Pico W." >&2
    exit 1
fi

echo
echo "Installing MicroPython dependencies..."
$MPREMOTE "${CONNECT[@]}" mip install umqtt.simple

echo
echo "Copying ClimateCube application..."

for source_file in "$PICO_DIR"/*.py; do
    file_name="$(basename "$source_file")"

    if [[ "$file_name" == "config.py" || "$file_name" == "config_template.py" ]]; then
        continue
    fi

    echo "  $file_name"
    $MPREMOTE "${CONNECT[@]}" cp "$source_file" :
done

echo "  config.py"
$MPREMOTE "${CONNECT[@]}" cp "$CONFIG_FILE" :config.py

echo
echo "Verifying image..."
$MPREMOTE "${CONNECT[@]}" exec \
    "from umqtt.simple import MQTTClient; import config, sensor, display; print('Broker:', config.BROKER); print('Image verification passed')"

echo
echo "Restarting Pico W..."
$MPREMOTE "${CONNECT[@]}" reset

echo
echo "===================================="
echo "Pico W imaging complete"
echo "===================================="
echo
echo "To watch startup, run:"
echo "  $MPREMOTE connect $PORT repl"
#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: The hub has local changes. Commit, stash, or discard them before deploying." >&2
    git status --short
    exit 1
fi

echo "Updating ClimateCube..."
git pull --ff-only

echo "Restarting MQTT listener..."
sudo systemctl restart climatecube-listener
sudo systemctl is-active --quiet climatecube-listener

echo "Restarting web server..."
sudo systemctl restart climatecube-web
sudo systemctl is-active --quiet climatecube-web

if systemctl cat climatecube-weather > /dev/null 2>&1; then
    echo "Restarting weather collector..."
    sudo systemctl restart climatecube-weather
    sudo systemctl is-active --quiet climatecube-weather
else
    echo "Weather collector is not installed; run ./scripts/setup.sh once to install it."
fi

echo
echo "ClimateCube deployment complete."
echo "Commit: $(git rev-parse --short HEAD)"
echo "MQTT listener: $(systemctl is-active climatecube-listener)"
echo "Web server:    $(systemctl is-active climatecube-web)"
echo "Weather:       $(systemctl is-active climatecube-weather 2>/dev/null || echo not-installed)"
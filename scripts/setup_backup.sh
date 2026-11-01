#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${SUDO_USER:-$(id -un)}"

if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "Usage: bash scripts/setup_backup.sh user@backup-host /absolute/backup/directory [keep-count]" >&2
    exit 1
fi

TARGET="$1"
REMOTE_DIR="$2"
KEEP="${3:-14}"
cd "$PROJECT_DIR"

if [[ "${TARGET##*@}" == "your-server" || "$REMOTE_DIR" == "/absolute/backup/path" || "$REMOTE_DIR" == "/absolute/backup/directory" ]]; then
    echo "ERROR: These are example values, not a configured backup destination." >&2
    echo "Use the SFTP account/hostname of a different computer or NAS and a real directory on that machine." >&2
    echo "Configure key-based SFTP access first; see README.md." >&2
    exit 1
fi

if ! command -v sftp > /dev/null; then
    echo "ERROR: Install the OpenSSH client first: sudo apt install openssh-client" >&2
    exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
    echo "ERROR: Run scripts/setup.sh first to set up the hub." >&2
    exit 1
fi

.venv/bin/python -c \
    'import sys; from services.database_backup import validate_destination; validate_destination(sys.argv[1], sys.argv[2], int(sys.argv[3]))' \
    "$TARGET" "$REMOTE_DIR" "$KEEP"

sudo install -m 600 /dev/null /etc/climatecube-backup.conf
sudo tee /etc/climatecube-backup.conf > /dev/null <<EOF
CLIMATECUBE_BACKUP_SFTP_TARGET=$TARGET
CLIMATECUBE_BACKUP_REMOTE_DIR=$REMOTE_DIR
CLIMATECUBE_BACKUP_KEEP=$KEEP
EOF

sudo tee /etc/systemd/system/climatecube-backup.service > /dev/null <<EOF
[Unit]
Description=ClimateCube off-device database backup
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=/etc/climatecube-backup.conf
Environment=PYTHONUNBUFFERED=1
UMask=0077
ExecStart=$PROJECT_DIR/.venv/bin/python -m services.database_backup
TimeoutStartSec=35min
EOF

sudo tee /etc/systemd/system/climatecube-backup.timer > /dev/null <<EOF
[Unit]
Description=Daily ClimateCube database backup

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=15min
Unit=climatecube-backup.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
echo "Testing the first off-device backup (SFTP must work without a password)..."
if ! sudo systemctl start climatecube-backup.service; then
    echo "ERROR: The first backup failed; the backup timer has not been enabled by this run." >&2
    sudo systemctl status climatecube-backup.service --no-pager --full || true
    sudo journalctl -u climatecube-backup.service -n 30 --no-pager
    exit 1
fi
sudo systemctl enable --now climatecube-backup.timer
sudo systemctl is-active --quiet climatecube-backup.timer
echo "Daily backups enabled; keeping $KEEP snapshots on $TARGET:$REMOTE_DIR"

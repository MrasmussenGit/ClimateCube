# ClimateCube

## Deploy the Hub

After pushing changes, connect to the Pi Zero hub and run:

	cd ~/ClimateCube
	./scripts/deploy_hub.sh

The deployment requires a clean working tree, performs a fast-forward-only Git
pull, restarts the MQTT listener so database migrations run before new messages
are processed, restarts the web server, and verifies both services are active.

The dashboard reports the database size and usable disk space remaining. It
displays a warning when space available to the service account falls below 10%
of the drive. Set `CLIMATECUBE_STORAGE_WARNING_PERCENT` in the web service
environment to use a different percentage. At 5%, the indicator and alert turn
red; configure that threshold with `CLIMATECUBE_STORAGE_CRITICAL_PERCENT`.

## Back Up and Restore the Hub Database

Backups are **opt-in** and must live on another computer or NAS to survive loss
of the Pi or its SD card. The SFTP backup option saves the entire SQLite database,
including readings, sensor metadata, outdoor weather, and settings. It uses
SQLite's live-backup API, so collection and the dashboard can keep running.
No cloud account or additional Python packages are needed. The hub uses the
OpenSSH `sftp` client; no shell commands or Python run on the receiving machine.

### Prepare a Synology NAS

1. In DSM, enable **SFTP** under **Control Panel → File Services → FTP**.
   SFTP is not plain FTP or FTPS. Do not expose the service to the internet;
   allow access from the hub on your local network.
2. Create a dedicated, non-admin backup user. Give it read/write access only
   to the backup shared folder and permit FTP/SFTP application access.
3. Configure public-key authentication for that user. Enable user homes if
   needed, then place the hub's **public** key in the user's
   `.ssh/authorized_keys` without overwriting existing keys. Protect `.ssh`
   with mode `700` and `authorized_keys` with mode `600`, owned by that user.
   Depending on DSM, an administrator may need to do this one-time setup.
   Never copy the hub's private key to the NAS.
4. Use an SFTP client to create a dedicated backup directory and confirm its
   absolute path **as seen over SFTP**. A NAS filesystem path and its SFTP
   path may differ; do not assume `/volume1/...` is visible to the account.

The same backup option works with any SFTP server supporting upload, download,
chmod, rename, directory listing, and delete. Password-only authentication is
not supported by the unattended job; verify key-based access before installing.

### Enable daily SFTP backups

Run these steps as the same hub user that runs ClimateCube, not as root.
The remote backup directory must already exist and be readable/writable.

1. Configure key-based SFTP access to the backup machine. Use an existing key,
   or create a dedicated unattended key (do not overwrite an existing key):

       ssh-keygen -t ed25519 -f ~/.ssh/climatecube_backup -N ""

   Install the public key on the server as described above. `ssh-copy-id` is
   not suitable for an SFTP-only account because it needs remote shell access.
   Add the following to `~/.ssh/config`, replacing the host/user/port with yours:

       Host climatecube-nas
           HostName YOUR_NAS_LOCAL_IP
           User YOUR_BACKUP_USER
           Port 22
           IdentityFile ~/.ssh/climatecube_backup

   Protect the private key and SSH configuration with owner-only permissions.
   Use a dedicated remote account with access only to the backup location.

2. Connect once interactively and verify the host fingerprint against the
   receiving machine before accepting it. Use `pwd` and `ls` to locate the
   backup directory, then `bye` to exit:

       sftp climatecube-nas

   Confirm unattended SFTP access works (enter `pwd`, then `bye`):

       sftp -o BatchMode=yes -o StrictHostKeyChecking=yes climatecube-nas

3. Install and test the backup job on the hub, replacing `REMOTE_SFTP_PATH`
   with the directory's actual absolute SFTP path:

       cd ~/ClimateCube
       bash scripts/setup_backup.sh climatecube-nas REMOTE_SFTP_PATH 14

   `climatecube-nas` is the SSH/SFTP alias configured above.
   These examples do not provision a backup server. Do not use the literal
   placeholder `backup@your-server` or `/absolute/backup/path`.
   On an existing hub, install `openssh-client` if it is missing.

The installer makes a first backup and only enables the timer if it succeeds.
If it fails, it prints the service status and recent journal entries so you can
identify DNS, SFTP authentication, host-key, permission, or receiver errors.
The timer runs daily near midnight in the hub's timezone, with up to 15 minutes
of random delay. A missed run is triggered after the hub boots. The latest
14 timestamped snapshots are kept **on the receiving machine**; older
ClimateCube snapshots are removed only after a new one is successfully
received and verified. Other filenames are not pruned. Do not share the
same remote directory between different hubs.

The connection verifies the SSH host key and never prompts for passwords.
Each backup is staged privately, downloaded again, and compared using SHA-256
before being renamed to its final filename. This verifies the uploaded bytes
without requiring SQLite on the NAS, at the cost of a second full transfer.
It temporarily needs space for two full databases on the hub (in its system
temporary directory) and one extra snapshot on the receiver. Backups are
encrypted in transit by SSH, but not encrypted at rest; protect the receiver's
disk and backup account accordingly.

### Run, monitor, or disable backups

    sudo systemctl start climatecube-backup.service
    systemctl list-timers climatecube-backup.timer --no-pager
    journalctl -u climatecube-backup.service --since today --no-pager
    systemctl show climatecube-backup.service -p Result -p ExecMainStatus

Failed transfers exit nonzero and appear in the journal; they do not remove
existing backups. Check the journal regularly: no email/push alert is configured.
If the receiver is offline, the next daily run tries again; there is no
immediate retry. Daily backups can lose up to a day's readings, or more during
an extended outage.

Configuration is stored outside Git in `/etc/climatecube-backup.conf`. Re-run
the installer to change the host, directory, or retention count. Normal hub
deployments preserve this configuration and the timer. Disable automatic
backups with:

    sudo systemctl disable --now climatecube-backup.timer

For a one-off backup without installing the timer:

    .venv/bin/python -m services.database_backup \
        --sftp-target climatecube-nas --remote-dir REMOTE_SFTP_PATH --keep 14

The former `--ssh-target` option and `CLIMATECUBE_BACKUP_SSH_TARGET` environment
variable remain accepted for compatibility, but now transfer over SFTP.
Re-run the installer after upgrading from the shell-based SSH implementation.
Concurrent backups of the same database are rejected via a local lock file.

### Restore on a rebuilt hub

Run `./scripts/setup.sh` on the rebuilt hub first. Download a chosen snapshot
from the backup host. In an interactive SFTP session, use the real path and
timestamped filename:

    sftp climatecube-nas

At the `sftp>` prompt:

    get REMOTE_SFTP_PATH/climatecube-TIMESTAMP-ID.db climatecube-restore.db
    bye

Move the downloaded file to `~/climatecube-restore.db` if it was saved
elsewhere, then check it from the hub's shell:

    sqlite3 -readonly ~/climatecube-restore.db "PRAGMA quick_check;"

**Continue only if the integrity check reports `ok`.** Stop every database
writer before restoring, and save the current database as a fallback:

    cd ~/ClimateCube
    sudo systemctl stop climatecube-backup.timer
    sudo systemctl stop climatecube-backup.service
    sudo systemctl stop climatecube-listener climatecube-web climatecube-weather
    sqlite3 data/climatecube.db ".backup 'data/climatecube-before-restore.db'"
    sqlite3 data/climatecube.db ".restore '$HOME/climatecube-restore.db'"
    sqlite3 -readonly data/climatecube.db "PRAGMA quick_check;"

On a rebuilt hub without backups configured, skip the two backup-unit stop
commands. After confirming `ok`, restart the services; existing schema
migrations run when the listener starts:

    sudo systemctl start climatecube-listener
    sudo systemctl start climatecube-web climatecube-weather
    sudo systemctl start climatecube-backup.timer

Only restart the backup timer if it was previously configured and enabled.
Confirm historical readings and settings in the dashboard. Do not run
`scripts/init_db.sh` during recovery: it deletes the database. Keep the fallback
until recovery is confirmed, and periodically practice restoring a snapshot on
a spare hub.

## Supported Hardware

ClimateCube currently supports these devices on the Pico W I2C bus:

- BME280 temperature, humidity, and pressure sensor
- BME688 temperature, humidity, pressure, and gas-resistance sensor
- Pimoroni MICS6814 three-channel gas sensor at address `0x19` or `0x18`
- SSD1306 OLED display at address `0x3C`
- EC11 rotary encoder with push button

Connect the bare EC11 encoder using the Pico's internal pull-ups:

| EC11 contact | Pico GPIO | Physical pin |
| --- | --- | --- |
| Encoder outer A | GP10 | 14 |
| Encoder common (middle) | GND | 18 |
| Encoder outer B | GP11 | 15 |
| Push-button contact | GND | 18 |
| Other push-button contact | GP12 | 16 |

Pressing the encoder takes and publishes an immediate reading without resetting
the regular reading schedule. Rotating it selects the OLED summary, environment,
and network/device pages. Swap A and B if the page direction feels reversed.

MICS6814 readings are stored and displayed as resistance trends for reducing,
oxidising, and NH3-sensitive channels. They are not displayed as ppm because
reliable concentration values require controlled calibration. Allow the sensor
heater time to stabilize before interpreting changes.

Dashboard status indicators use these default ranges:

- Temperature: below 10°C very cold, 10-18°C cool, 18-26°C comfortable,
	26-32°C warm, and above 32°C hot.
- Relative humidity: below 20% very dry, 20-30% dry, 30-60% comfortable,
	60-70% humid, and above 70% very humid.
- Pressure: below 980 hPa low, 980-1035 hPa typical, and above 1035 hPa high.
	Pressure status describes weather conditions, not a personal safety limit.
- Gas resistance: learns from 30 prior samples in the last six hours. Changes
	within 5% are normal fluctuation, 5-20% are small, 20-50% are notable, and
	changes above 50% are large. Gas status chips show the exact percentage above
	or below the six-hour baseline. These are resistance trend indicators, not
	calibrated gas alarms.

After enough recent samples are available, status chips also show `↑`, `→`, or
`↓` relative to the prior six-hour average. To avoid arrows changing with normal
sensor noise, steady dead bands are ±0.5°C for temperature, ±2% for humidity,
±0.5 hPa for pressure, and ±5% for resistance. A rising pressure arrow commonly
indicates improving weather, while falling pressure commonly precedes unsettled
weather; local conditions can differ.

New numeric sensor types use the generic measurement pipeline and do not need
new database columns or dashboard markup. See `docs/SensorDrivers.md` for the
driver contract.

## Configure Outdoor Weather

ClimateCube collects outdoor conditions from Open-Meteo every 15 minutes and
stores each observation locally for indoor/outdoor history comparisons. Open
the dashboard Settings page and enter a 5-digit US ZIP code. ClimateCube uses
Zippopotam to resolve the ZIP code to approximate coordinates; manual latitude
and longitude remain available under Advanced settings.

Use **Compare rooms and outdoor weather** on the dashboard to layer selected
room sensors and outdoor temperature on one chart. The comparison view includes
individual sensor toggles plus **Add all** and **Clear all** actions, and keeps
the selection on that browser between visits. Use **Remove outliers** on either
history view to hide isolated spikes independently across every charted
measurement without deleting stored sensor readings; **Show raw data** restores
every point.

Each sensor history page links to **Correlation insights**, which aligns
15-minute indoor and outdoor observations over 7, 30, or 90 days. The analysis
reports Pearson and Spearman correlations, correlations between consecutive
changes, outdoor-leading response lags, repeating time-of-day effects,
scatterplots, data coverage, and reliability warnings. These are exploratory
associations rather than proof of causation.

Open-Meteo does not require an account or API key for non-commercial use within
its published usage limits. Review its current licence and pricing before using
ClimateCube commercially.

The collector runs as `climatecube-weather.service`. Existing hubs upgraded
from an earlier ClimateCube release must run `./scripts/setup.sh` once to
install that service. Useful checks are:

	systemctl status climatecube-weather --no-pager
	journalctl -u climatecube-weather --since today --no-pager

## Image a Pico W

For a fresh board, first flash the current Raspberry Pi Pico W MicroPython UF2.

Connect the Pico W by USB and run:

	./scripts/image_pico.sh

The imaging script verifies the board type, installs `umqtt.simple` and the
BME680/BME688 sensor driver, copies all ClimateCube files including the
MICS6814 driver without copying `__pycache__`, verifies the installation, and
restarts the Pico. It securely prompts for Wi-Fi settings, hides the
password while it is entered, and removes its temporary configuration after
imaging. The imaging computer finds the MQTT server at `climatecube.local` and
writes its current IP address to the Pico, so customers do not need to know or
enter it. Sensitive values do not need to be stored in the repository workspace.
If an older `pico/config.py` contains credentials, delete it after confirming
the new imaging workflow; Git ignores it, but it remains readable locally.

If multiple boards are connected, select one explicitly:

	./scripts/image_pico.sh --port /dev/ttyACM0

For unattended provisioning, use a protected configuration stored outside the
repository and restrict it to its owner with `chmod 600`:

	./scripts/image_pico.sh --config /path/to/customer-config.py
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

## Configure Outdoor Weather

ClimateCube collects outdoor conditions from Open-Meteo every 15 minutes and
stores each observation locally for indoor/outdoor history comparisons. Open
the dashboard Settings page and enter a 5-digit US ZIP code. ClimateCube uses
Zippopotam to resolve the ZIP code to approximate coordinates; manual latitude
and longitude remain available under Advanced settings.

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
BME680/BME688 sensor driver, copies all
ClimateCube files without copying `__pycache__`, verifies the installation, and
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
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
the selection on that browser between visits.

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
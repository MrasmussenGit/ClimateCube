# ClimateCube

## Image a Pico W

For a fresh board, first flash the current Raspberry Pi Pico W MicroPython UF2.

Connect the Pico W by USB and run:

	./scripts/image_pico.sh

The imaging script verifies the board type, installs `umqtt.simple`, copies all
ClimateCube files without copying `__pycache__`, verifies the installation, and
restarts the Pico. It securely prompts for Wi-Fi settings, hides the
password while it is entered, and removes its temporary configuration after
imaging. The MQTT server is found at `climatecube.local`, so customers do not
need to know or enter its address. Sensitive values do not need to be stored in the repository workspace.
If an older `pico/config.py` contains credentials, delete it after confirming
the new imaging workflow; Git ignores it, but it remains readable locally.

If multiple boards are connected, select one explicitly:

	./scripts/image_pico.sh --port /dev/ttyACM0

For unattended provisioning, use a protected configuration stored outside the
repository and restrict it to its owner with `chmod 600`:

	./scripts/image_pico.sh --config /path/to/customer-config.py
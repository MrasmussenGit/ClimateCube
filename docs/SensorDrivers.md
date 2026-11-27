# Sensor Driver Pattern

ClimateCube sensor drivers return hardware names and measurement descriptors.
The Pico publishes those descriptors over MQTT, the listener stores them in
generic tables, and the dashboard and history page render them from metadata.

## Pico Driver Contract

Optional drivers live in `pico/` and expose a `read()` function. Register a new
module in `OPTIONAL_DRIVERS` in `pico/sensor_manager.py`.

`read()` returns `None` when hardware is absent or temporarily unavailable.
Otherwise it returns this shape:

```python
{
    "hardware": ["Example Sensor"],
    "measurements": [
        {
            "key": "example_measurement",
            "label": "Example measurement",
            "value": 12.34,
            "unit": "units",
            "precision": 2,
            "format": "number",
            "order": 100
        }
    ]
}
```

Keys must begin with a lowercase letter and contain only lowercase letters,
digits, and underscores. Keep keys stable after release. Supported display
formats are `number`, `resistance`, and `temperature`.

An optional driver must catch expected I2C and runtime failures and return
`None`, so it cannot stop the required environmental sensor from reporting.

## Environmental Sensor Recovery

The required BME280/BME688 driver treats an I2C error or conversion timeout as
an unavailable reading, not proof that the hardware is disconnected. It drops
the failed driver instance and re-scans/reinitializes on the next attempt.
I2C construction and scanning are covered by the same error handling as sensor
initialization, so a failed scan cannot terminate the reading loop. OLED
initialization also handles I2C failures on the shared bus.

The OLED shows `Sensor read unavailable` while the main loop retries after
10 seconds, then 30 seconds, then every 60 seconds. No stale reading is
published. The Pico's rotating `boot.log` records each failed attempt with the
driver's reason (scan addresses, initialization error, or read error), followed
by a recovery message when reporting resumes. `boot.log.old` holds the previous
log segment. OLED initialization errors are printed on the serial console.

Before resetting a failing device, preserve both logs over USB with `mpremote`
(connecting interrupts the running program; reset it afterwards):

```sh
.venv/bin/mpremote connect /dev/ttyACM0 fs cp :boot.log ./pico-boot.log
.venv/bin/mpremote connect /dev/ttyACM0 fs cp :boot.log.old ./pico-boot.log.old
.venv/bin/mpremote connect /dev/ttyACM0 reset
```

Select the actual serial port; the old log may not exist yet. Existing firmware
logs may only say `Environmental sensor not detected`; install the updated Pico
firmware to capture detailed errors. Hub deployment alone does not update Picos.
Do not treat a successful reset as proof of a software-only issue: intermittent
power, connectors, pull-ups, and I2C wiring can still cause read/scan failures.
These retries do not power-cycle the sensor or guarantee recovery of a physically
stuck bus.

## Hub Storage

`measurement_definition` stores labels, units, precision, formatting, and
display order once per key. `sensor_measurement` stores each numeric value
against its parent `sensor_reading`. Existing fixed environmental columns remain
for compatibility and optimized temperature-history queries.

The MQTT listener validates descriptor keys and finite numeric values. New
generic measurements then appear on the dashboard and per-sensor history page
without SQL or template changes.
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

## Hub Storage

`measurement_definition` stores labels, units, precision, formatting, and
display order once per key. `sensor_measurement` stores each numeric value
against its parent `sensor_reading`. Existing fixed environmental columns remain
for compatibility and optimized temperature-history queries.

The MQTT listener validates descriptor keys and finite numeric values. New
generic measurements then appear on the dashboard and per-sensor history page
without SQL or template changes.
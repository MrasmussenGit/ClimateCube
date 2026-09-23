import json
import sqlite3
from bisect import bisect_left
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = PROJECT_DIR / "data" / "climatecube.db"

HISTORY_RANGES = {
    "6h": ("-6 hours", 60),
    "24h": ("-24 hours", 300),
    "3d": ("-3 days", 900),
    "7d": ("-7 days", 1800)
}

INSIGHT_RANGES = {
    "7d": "-7 days",
    "30d": "-30 days",
    "90d": "-90 days"
}

INSIGHT_BUCKET_SECONDS = 900


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_weather_schema():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS weather_observation (
                observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                observed_ts DATETIME NOT NULL,
                insert_ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                provider TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                temperature_c REAL NOT NULL,
                humidity_pct REAL NOT NULL,
                dew_point_c REAL,
                pressure_hpa REAL,
                precipitation_mm REAL,
                wind_speed_kmh REAL,
                cloud_cover_pct REAL,
                weather_code INTEGER,
                UNIQUE(provider, observed_ts, latitude, longitude)
            );
            CREATE INDEX IF NOT EXISTS idx_weather_observation_time
            ON weather_observation(observed_ts);
            CREATE TABLE IF NOT EXISTS app_setting (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL
            );
            """
        )


def ensure_measurement_schema():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS measurement_definition (
                measurement_key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                unit TEXT NOT NULL,
                precision_digits INTEGER NOT NULL DEFAULT 2,
                display_format TEXT NOT NULL DEFAULT 'number',
                display_order INTEGER NOT NULL DEFAULT 100
            );
            CREATE TABLE IF NOT EXISTS sensor_measurement (
                reading_id INTEGER NOT NULL,
                measurement_key TEXT NOT NULL,
                measurement_value REAL NOT NULL,
                PRIMARY KEY (reading_id, measurement_key),
                FOREIGN KEY (reading_id)
                    REFERENCES sensor_reading(reading_id) ON DELETE CASCADE,
                FOREIGN KEY (measurement_key)
                    REFERENCES measurement_definition(measurement_key)
            );
            CREATE INDEX IF NOT EXISTS idx_sensor_measurement_key_reading
            ON sensor_measurement(measurement_key, reading_id);
            """
        )


def format_measurement_value(value, unit, precision, display_format):
    if display_format == "resistance":
        if value >= 1000000:
            return "{:.{}f} MΩ".format(value / 1000000, precision)
        if value >= 1000:
            return "{:.{}f} kΩ".format(value / 1000, precision)
        return "{:.{}f} Ω".format(value, precision)

    return "{:.{}f}{}{}".format(
        value,
        precision,
        " " if unit else "",
        unit
    )


MEASUREMENT_DESCRIPTIONS = {
    "temperature_c": (
        "Air temperature measures how warm or cold the air is."
    ),
    "humidity_pct": (
        "Relative humidity is the amount of moisture in the air compared "
        "with the maximum it can hold at the current temperature."
    ),
    "pressure_hpa": (
        "Atmospheric pressure is the force exerted by the air. Rising "
        "pressure often accompanies improving weather; falling pressure "
        "can precede unsettled weather."
    ),
    "bme688_gas_resistance_ohms": (
        "The BME688 is a broad air-quality sensor. Its heated sensing surface "
        "changes electrical resistance when exposed to mixtures of volatile "
        "organic compounds and other gases, but it cannot identify a specific "
        "chemical or report a concentration. Cooking, cleaners, fragrances, "
        "humidity, temperature, and sensor warm-up can all move the reading. "
        "Treat departures from this sensor's own normal baseline as relative "
        "air-quality clues only. This is not a smoke, carbon-monoxide, natural-"
        "gas, or life-safety alarm."
    ),
    "mics6814_reducing_ohms": (
        "The MiCS-6814 reducing channel can respond to carbon monoxide, "
        "hydrogen, ethanol, and other reducing gases. It is cross-sensitive, "
        "so this graph cannot identify which gas caused a change or convert "
        "resistance into a trustworthy ppm concentration without controlled "
        "calibration and environmental compensation. Carbon monoxide can be "
        "deadly, but this channel must never replace a listed carbon-monoxide "
        "alarm. Use it only for relative comparisons with this sensor's own "
        "baseline."
    ),
    "mics6814_oxidising_ohms": (
        "The MiCS-6814 oxidising channel is sensitive to oxidising gases such "
        "as nitrogen dioxide and can also react to other chemicals and changing "
        "environmental conditions. Nitrogen dioxide can irritate and damage "
        "the respiratory system, but resistance alone does not establish a "
        "gas identity or safe exposure level. Use changes relative to this "
        "sensor's normal baseline for investigation, not as a safety alarm."
    ),
    "mics6814_nh3_ohms": (
        "The MiCS-6814 NH3 channel is designed to respond strongly to ammonia, "
        "but it is also cross-sensitive to other gases and affected by its "
        "environment. Ammonia can irritate or burn the eyes, skin, and lungs "
        "at hazardous concentrations; this resistance reading cannot determine "
        "that concentration or confirm safety. Use only relative changes from "
        "this sensor's own baseline and rely on appropriate calibrated detectors "
        "for exposure or emergency decisions."
    )
}


def get_measurement_description(key, label):
    if key in MEASUREMENT_DESCRIPTIONS:
        return MEASUREMENT_DESCRIPTIONS[key]
    if key.endswith("_ohms"):
        return (
            label + " is an electrical resistance reported by a gas sensor. "
            "Use changes as a relative trend, not as a calibrated concentration "
            "or safety alarm."
        )
    return label + " is the current value reported by this sensor."


def add_measurement_trend(status, key, value, baseline, baseline_count):
    minimum_samples = 30 if key.endswith("_ohms") else 3
    if baseline_count < minimum_samples or baseline is None:
        return status

    if key == "temperature_c":
        threshold = 0.5
    elif key == "humidity_pct":
        threshold = 2.0
    elif key == "pressure_hpa":
        threshold = 0.5
    elif key.endswith("_ohms"):
        threshold = abs(baseline) * 0.05
    else:
        threshold = max(abs(baseline) * 0.02, 0.01)

    difference = value - baseline
    if difference > threshold:
        trend, symbol, trend_label = "up", "↑", "Rising"
    elif difference < -threshold:
        trend, symbol, trend_label = "down", "↓", "Falling"
    else:
        trend, symbol, trend_label = "steady", "→", "Steady"

    status.update({
        "trend": trend,
        "trend_symbol": symbol,
        "trend_label": trend_label
    })
    if key.endswith("_ohms") and baseline:
        change_percent = difference / baseline * 100
        if change_percent > 0:
            comparison = "above"
        elif change_percent < 0:
            comparison = "below"
        else:
            comparison = "at"
        status.update({
            "baseline_change_pct": round(abs(change_percent), 1),
            "baseline_comparison": comparison,
            "baseline_change_label": "{:.1f}% {} the six-hour baseline".format(
                abs(change_percent), comparison
            )
        })
    return status


def classify_measurement(key, value, baseline=None, baseline_count=0):
    if key == "temperature_c":
        if value < 10:
            status = {"level": "critical", "label": "Very cold"}
        elif value < 18:
            status = {"level": "warning", "label": "Cool"}
        elif value <= 26:
            status = {"level": "normal", "label": "Comfortable"}
        elif value <= 32:
            status = {"level": "warning", "label": "Warm"}
        else:
            status = {"level": "critical", "label": "Hot"}
        return add_measurement_trend(
            status, key, value, baseline, baseline_count
        )

    if key == "humidity_pct":
        if value < 20:
            status = {"level": "critical", "label": "Very dry"}
        elif value < 30:
            status = {"level": "warning", "label": "Dry"}
        elif value <= 60:
            status = {"level": "normal", "label": "Comfortable"}
        elif value <= 70:
            status = {"level": "warning", "label": "Humid"}
        else:
            status = {"level": "critical", "label": "Very humid"}
        return add_measurement_trend(
            status, key, value, baseline, baseline_count
        )

    if key == "pressure_hpa":
        if value < 980:
            status = {"level": "info", "label": "Low pressure"}
        elif value <= 1035:
            status = {"level": "normal", "label": "Typical"}
        else:
            status = {"level": "info", "label": "High pressure"}
        return add_measurement_trend(
            status, key, value, baseline, baseline_count
        )

    if key.endswith("_ohms"):
        if baseline_count < 30 or not baseline:
            return {"level": "learning", "label": "Learning baseline"}

        change = abs(value - baseline) / abs(baseline)
        if change <= 0.05:
            status = {"level": "normal", "label": "Normal fluctuation"}
        elif change <= 0.2:
            status = {"level": "info", "label": "Small change"}
        elif change <= 0.5:
            status = {"level": "warning", "label": "Notable change"}
        else:
            status = {"level": "warning", "label": "Large change"}
        return add_measurement_trend(
            status, key, value, baseline, baseline_count
        )

    return {"level": "info", "label": "Current reading"}


def get_legacy_measurements(reading):
    definitions = [
        ("temperature_c", "Temperature", reading["temperature_c"], "°C", 2, "temperature", 10),
        ("humidity_pct", "Humidity", reading["humidity_pct"], "%", 2, "number", 20),
        ("pressure_hpa", "Pressure", reading["pressure_hpa"], "hPa", 2, "number", 30),
        ("bme688_gas_resistance_ohms", "BME688 gas resistance", reading["gas_resistance_ohms"], "Ω", 2, "resistance", 40)
    ]
    return [
        {
            "key": key,
            "label": label,
            "value": value,
            "unit": unit,
            "precision": precision,
            "format": display_format,
            "order": display_order,
            "description": get_measurement_description(key, label),
            "status": classify_measurement(key, value),
            "display_value": format_measurement_value(
                value, unit, precision, display_format
            )
        }
        for key, label, value, unit, precision, display_format, display_order
        in definitions
        if value is not None
    ]


def add_latest_measurements(readings):
    if not readings:
        return readings

    ensure_measurement_schema()
    reading_ids = [reading["reading_id"] for reading in readings]
    placeholders = ",".join("?" for _ in reading_ids)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                sm.reading_id,
                sm.measurement_key AS key,
                md.label,
                sm.measurement_value AS value,
                md.unit,
                md.precision_digits AS precision,
                md.display_format AS format,
                md.display_order AS display_order
            FROM sensor_measurement AS sm
            JOIN measurement_definition AS md
                ON md.measurement_key = sm.measurement_key
            WHERE sm.reading_id IN ({})
            ORDER BY md.display_order, md.label
            """.format(placeholders),
            reading_ids
        ).fetchall()
        baseline_rows = conn.execute(
            """
            SELECT
                r.sensor_id,
                sm.measurement_key,
                AVG(sm.measurement_value) AS baseline,
                COUNT(*) AS baseline_count
            FROM sensor_measurement AS sm
            JOIN sensor_reading AS r ON r.reading_id = sm.reading_id
            WHERE r.reading_id NOT IN ({})
              AND datetime(replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' '))
                  >= datetime('now', '-6 hours')
            GROUP BY r.sensor_id, sm.measurement_key
            """.format(placeholders),
            reading_ids
        ).fetchall()

    baselines = {
        (row["sensor_id"], row["measurement_key"]): (
            row["baseline"], row["baseline_count"]
        )
        for row in baseline_rows
    }

    measurements_by_reading = {reading_id: [] for reading_id in reading_ids}
    for row in rows:
        measurement = dict(row)
        reading_id = measurement.pop("reading_id")
        measurement["order"] = measurement.pop("display_order")
        measurement["description"] = get_measurement_description(
            measurement["key"], measurement["label"]
        )
        measurement["display_value"] = format_measurement_value(
            measurement["value"],
            measurement["unit"],
            measurement["precision"],
            measurement["format"]
        )
        measurements_by_reading[reading_id].append(measurement)

    for reading in readings:
        measurements = measurements_by_reading[reading["reading_id"]]
        if not measurements:
            measurements = get_legacy_measurements(reading)
        for measurement in measurements:
            baseline, baseline_count = baselines.get(
                (reading["sensor_id"], measurement["key"]),
                (None, 0)
            )
            measurement["status"] = classify_measurement(
                measurement["key"],
                measurement["value"],
                baseline,
                baseline_count
            )
        reading["measurements"] = measurements
        reading["secondary_measurements"] = [
            measurement for measurement in measurements
            if measurement["key"] != "temperature_c"
        ]
        reading["temperature_status"] = next(
            (
                measurement["status"] for measurement in measurements
                if measurement["key"] == "temperature_c"
            ),
            classify_measurement("temperature_c", reading["temperature_c"])
        )
        reading.pop("reading_id")

    return readings


def get_weather_settings():
    ensure_weather_schema()

    with get_connection() as conn:
        settings = {
            row["setting_key"]: row["setting_value"]
            for row in conn.execute(
                """
                SELECT setting_key, setting_value
                FROM app_setting
                WHERE setting_key LIKE 'weather_%'
                """
            )
        }

    return {
        "latitude": settings.get("weather_latitude", ""),
        "longitude": settings.get("weather_longitude", ""),
        "zip_code": settings.get("weather_zip_code", ""),
        "place_name": settings.get("weather_place_name", ""),
        "state": settings.get("weather_state", ""),
        "location_name": settings.get(
            "weather_location_name",
            "Outdoor Weather"
        )
    }


def update_weather_settings(
    latitude,
    longitude,
    location_name,
    zip_code="",
    place_name="",
    state=""
):
    ensure_weather_schema()
    values = {
        "weather_latitude": str(latitude),
        "weather_longitude": str(longitude),
        "weather_location_name": location_name,
        "weather_zip_code": zip_code,
        "weather_place_name": place_name,
        "weather_state": state
    }

    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO app_setting (setting_key, setting_value)
            VALUES (?, ?)
            ON CONFLICT(setting_key)
            DO UPDATE SET setting_value = excluded.setting_value
            """,
            values.items()
        )


def get_latest_weather():
    ensure_weather_schema()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM weather_observation
            ORDER BY observed_ts DESC
            LIMIT 1
            """
        ).fetchone()
        baseline = conn.execute(
            """
            SELECT
                AVG(temperature_c) AS temperature_c,
                AVG(humidity_pct) AS humidity_pct,
                AVG(pressure_hpa) AS pressure_hpa,
                COUNT(*) AS sample_count
            FROM weather_observation
            WHERE observation_id NOT IN
                (SELECT observation_id FROM weather_observation
                 ORDER BY observed_ts DESC LIMIT 1)
              AND datetime(observed_ts) >= datetime('now', '-6 hours')
            """
        ).fetchone()

    if row is None:
        return None

    weather = dict(row)
    weather["location_name"] = get_weather_settings()["location_name"]
    weather["temperature_status"] = classify_measurement(
        "temperature_c", weather["temperature_c"],
        baseline["temperature_c"], baseline["sample_count"]
    )
    weather["humidity_status"] = classify_measurement(
        "humidity_pct", weather["humidity_pct"],
        baseline["humidity_pct"], baseline["sample_count"]
    )
    if weather["pressure_hpa"] is not None:
        weather["pressure_status"] = classify_measurement(
            "pressure_hpa", weather["pressure_hpa"],
            baseline["pressure_hpa"], baseline["sample_count"]
        )
    return weather


def get_latest_readings(include_inactive=False):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                r.reading_id,
                s.sensor_id,
                s.sensor_name,
                s.device_id,
                s.ip_address,
                s.active_flag,
                s.reading_interval_sec,
                s.hardware_json,
                r.pico_ts AS reading_time,
                r.insert_ts AS last_contact_time,
                r.temperature_c,
                r.humidity_pct,
                r.pressure_hpa,
                r.gas_resistance_ohms
            FROM sensor_reading AS r
            JOIN sensor AS s
                ON s.sensor_id = r.sensor_id
            WHERE r.reading_id IN
            (
                SELECT MAX(reading_id)
                FROM sensor_reading
                GROUP BY sensor_id
            )
              AND (? = 1 OR s.active_flag = 1)
            ORDER BY s.sensor_name
            """,
            (1 if include_inactive else 0,)
        ).fetchall()

    readings = []

    hardware_names = {
        "bme280": "BME280",
        "bme688": "BME688",
        "mics6814": "MICS6814",
        "oled": "OLED"
    }

    for row in rows:
        reading = dict(row)
        hardware_json = reading.pop("hardware_json", None)

        try:
            hardware = json.loads(hardware_json) if hardware_json else None
            if isinstance(hardware, dict):
                hardware = [
                    hardware_names.get(key, key)
                    for key, present in hardware.items() if present
                ]
            reading["hardware"] = hardware
        except (TypeError, json.JSONDecodeError):
            reading["hardware"] = None

        readings.append(reading)

    return add_latest_measurements(readings)


def get_sensor(sensor_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT sensor_id, sensor_name, device_id, ip_address
            FROM sensor
            WHERE sensor_id = ?
            """,
            (sensor_id,)
        ).fetchone()

    return dict(row) if row else None


def get_sensors():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.sensor_id,
                s.sensor_name,
                s.device_id,
                s.ip_address,
                s.active_flag,
                MAX(COALESCE(r.pico_ts, r.insert_ts)) AS last_reading_time
            FROM sensor AS s
            LEFT JOIN sensor_reading AS r
                ON r.sensor_id = s.sensor_id
            GROUP BY
                s.sensor_id,
                s.sensor_name,
                s.device_id,
                s.ip_address,
                s.active_flag
            ORDER BY s.sensor_name
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_hidden_sensor_count():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM sensor WHERE active_flag = 0"
        ).fetchone()

    return row["count"]


def update_sensor_name(sensor_id, sensor_name):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE sensor
            SET sensor_name = ?
            WHERE sensor_id = ?
            """,
            (sensor_name, sensor_id)
        )

    return cursor.rowcount == 1


def update_sensor_visibility(sensor_id, is_visible):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE sensor
            SET active_flag = ?
            WHERE sensor_id = ?
            """,
            (1 if is_visible else 0, sensor_id)
        )

    return cursor.rowcount == 1


def get_temperature_history(sensor_id, range_name):
    modifier, bucket_seconds = HISTORY_RANGES[range_name]

    with get_connection() as conn:
        rows = conn.execute(
            """
            WITH latest AS
            (
                SELECT MAX(COALESCE(pico_ts, insert_ts)) AS latest_ts
                FROM sensor_reading
                WHERE sensor_id = ?
            )
            SELECT
                MAX(COALESCE(r.pico_ts, r.insert_ts)) AS reading_time,
                AVG(r.temperature_c) AS temperature_c,
                AVG(r.humidity_pct) AS humidity_pct,
                AVG(r.pressure_hpa) AS pressure_hpa,
                AVG(r.gas_resistance_ohms) AS gas_resistance_ohms
            FROM sensor_reading AS r
            CROSS JOIN latest
            WHERE r.sensor_id = ?
              AND datetime(
                    replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                  ) >= datetime(
                    replace(latest.latest_ts, 'T', ' '), ?
                  )
            GROUP BY
                CAST(
                    strftime(
                        '%s',
                        replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                    ) AS INTEGER
                ) / ?
            ORDER BY reading_time
            """,
            (sensor_id, sensor_id, modifier, bucket_seconds)
        ).fetchall()

    return [dict(row) for row in rows]


def get_additional_measurement_history(sensor_id, range_name):
    modifier, bucket_seconds = HISTORY_RANGES[range_name]
    ensure_measurement_schema()

    with get_connection() as conn:
        rows = conn.execute(
            """
            WITH latest AS
            (
                SELECT MAX(COALESCE(pico_ts, insert_ts)) AS latest_ts
                FROM sensor_reading
                WHERE sensor_id = ?
            )
            SELECT
                MAX(COALESCE(r.pico_ts, r.insert_ts)) AS reading_time,
                sm.measurement_key AS key,
                md.label,
                md.unit,
                md.precision_digits AS precision,
                md.display_format AS format,
                md.display_order AS display_order,
                AVG(sm.measurement_value) AS value
            FROM sensor_measurement AS sm
            JOIN sensor_reading AS r ON r.reading_id = sm.reading_id
            JOIN measurement_definition AS md
                ON md.measurement_key = sm.measurement_key
            CROSS JOIN latest
            WHERE r.sensor_id = ?
              AND sm.measurement_key NOT IN
                  ('temperature_c', 'humidity_pct', 'pressure_hpa')
              AND datetime(
                    replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                  ) >= datetime(
                    replace(latest.latest_ts, 'T', ' '), ?
                  )
            GROUP BY
                sm.measurement_key,
                CAST(
                    strftime(
                        '%s',
                        replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                    ) AS INTEGER
                ) / ?
            ORDER BY md.display_order, reading_time
            """,
            (sensor_id, sensor_id, modifier, bucket_seconds)
        ).fetchall()

    measurements = []

    for row in rows:
        measurement = dict(row)
        measurement["description"] = get_measurement_description(
            measurement["key"],
            measurement["label"]
        )
        measurements.append(measurement)

    return measurements


def get_temperature_comparison(range_name):
    modifier, bucket_seconds = HISTORY_RANGES[range_name]

    with get_connection() as conn:
        rows = conn.execute(
            """
            WITH latest AS
            (
                SELECT MAX(COALESCE(r.pico_ts, r.insert_ts)) AS latest_ts
                FROM sensor_reading AS r
                JOIN sensor AS s ON s.sensor_id = r.sensor_id
                WHERE s.active_flag = 1
            ), bucketed AS
            (
                SELECT
                    r.sensor_id,
                    s.sensor_name,
                    CAST(
                        strftime(
                            '%s',
                            replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                        ) AS INTEGER
                    ) / ? AS bucket,
                    AVG(r.temperature_c) AS temperature_c
                FROM sensor_reading AS r
                JOIN sensor AS s ON s.sensor_id = r.sensor_id
                CROSS JOIN latest
                WHERE s.active_flag = 1
                  AND datetime(
                        replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                      ) >= datetime(
                        replace(latest.latest_ts, 'T', ' '), ?
                      )
                GROUP BY r.sensor_id, s.sensor_name, bucket
            )
            SELECT
                sensor_id,
                sensor_name,
                datetime(bucket * ?, 'unixepoch') AS reading_time,
                temperature_c
            FROM bucketed
            ORDER BY reading_time, sensor_name
            """,
            (bucket_seconds, modifier, bucket_seconds)
        ).fetchall()

    return [dict(row) for row in rows]


def add_outdoor_comparison(readings):
    if not readings:
        return readings

    ensure_weather_schema()
    reading_times = [
        datetime.fromisoformat(reading["reading_time"].replace("T", " "))
        for reading in readings
    ]

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT observed_ts, temperature_c, humidity_pct, dew_point_c
            FROM weather_observation
            WHERE datetime(observed_ts) BETWEEN datetime(?, '-30 minutes')
                                           AND datetime(?, '+30 minutes')
            ORDER BY observed_ts
            """,
            (readings[0]["reading_time"], readings[-1]["reading_time"])
        ).fetchall()

    weather = [dict(row) for row in rows]

    for reading, reading_time in zip(readings, reading_times):
        nearest = min(
            weather,
            key=lambda item: abs(
                datetime.fromisoformat(item["observed_ts"]) - reading_time
            ),
            default=None
        )

        if nearest is None or abs(
            datetime.fromisoformat(nearest["observed_ts"]) - reading_time
        ).total_seconds() > 1800:
            reading["outdoor_temperature_c"] = None
            reading["outdoor_humidity_pct"] = None
            reading["outdoor_dew_point_c"] = None
            continue

        reading["outdoor_temperature_c"] = nearest["temperature_c"]
        reading["outdoor_humidity_pct"] = nearest["humidity_pct"]
        reading["outdoor_dew_point_c"] = nearest["dew_point_c"]

    return readings


def get_correlation_observations(sensor_id, range_name):
        modifier = INSIGHT_RANGES[range_name]
        ensure_weather_schema()
        ensure_measurement_schema()

        with get_connection() as conn:
            indoor_rows = conn.execute(
                """
                WITH latest AS
                (
                    SELECT MAX(COALESCE(pico_ts, insert_ts)) AS latest_ts
                    FROM sensor_reading
                    WHERE sensor_id = ?
                ), bucketed AS
                (
                    SELECT
                        CAST(
                            strftime(
                                '%s',
                                replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                            ) AS INTEGER
                        ) / ? AS bucket,
                        AVG(r.temperature_c) AS temperature_c,
                        AVG(r.humidity_pct) AS humidity_pct,
                        AVG(r.pressure_hpa) AS pressure_hpa
                    FROM sensor_reading AS r
                    CROSS JOIN latest
                    WHERE r.sensor_id = ?
                      AND datetime(
                            replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                          ) >= datetime(
                            replace(latest.latest_ts, 'T', ' '), ?
                          )
                    GROUP BY bucket
                )
                SELECT
                    datetime(bucket * ?, 'unixepoch') AS reading_time,
                    temperature_c,
                    humidity_pct,
                    pressure_hpa
                FROM bucketed
                ORDER BY reading_time
                """,
                (
                    sensor_id,
                    INSIGHT_BUCKET_SECONDS,
                    sensor_id,
                    modifier,
                    INSIGHT_BUCKET_SECONDS
                )
            ).fetchall()

            measurement_rows = conn.execute(
                """
                WITH latest AS
                (
                    SELECT MAX(COALESCE(pico_ts, insert_ts)) AS latest_ts
                    FROM sensor_reading
                    WHERE sensor_id = ?
                ), bucketed AS
                (
                    SELECT
                        CAST(
                            strftime(
                                '%s',
                                replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                            ) AS INTEGER
                        ) / ? AS bucket,
                        sm.measurement_key AS key,
                        md.label,
                        md.unit,
                        md.display_order,
                        AVG(sm.measurement_value) AS value
                    FROM sensor_measurement AS sm
                    JOIN sensor_reading AS r ON r.reading_id = sm.reading_id
                    JOIN measurement_definition AS md
                        ON md.measurement_key = sm.measurement_key
                    CROSS JOIN latest
                    WHERE r.sensor_id = ?
                      AND sm.measurement_key NOT IN
                          ('temperature_c', 'humidity_pct', 'pressure_hpa')
                      AND datetime(
                            replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                          ) >= datetime(
                            replace(latest.latest_ts, 'T', ' '), ?
                          )
                    GROUP BY bucket, sm.measurement_key
                )
                SELECT
                    datetime(bucket * ?, 'unixepoch') AS reading_time,
                    key,
                    label,
                    unit,
                    display_order,
                    value
                FROM bucketed
                ORDER BY display_order, reading_time
                """,
                (
                    sensor_id,
                    INSIGHT_BUCKET_SECONDS,
                    sensor_id,
                    modifier,
                    INSIGHT_BUCKET_SECONDS
                )
            ).fetchall()

            if indoor_rows:
                weather_rows = conn.execute(
                    """
                    SELECT
                        observed_ts,
                        temperature_c,
                        humidity_pct,
                        dew_point_c,
                        pressure_hpa,
                        precipitation_mm,
                        wind_speed_kmh,
                        cloud_cover_pct
                    FROM weather_observation
                    WHERE datetime(observed_ts)
                        BETWEEN datetime(?, '-30 minutes')
                            AND datetime(?, '+30 minutes')
                    ORDER BY observed_ts
                    """,
                    (
                        indoor_rows[0]["reading_time"],
                        indoor_rows[-1]["reading_time"]
                    )
                ).fetchall()
            else:
                weather_rows = []

        indoor_metrics = {
            "temperature_c": {
                "label": "Indoor temperature",
                "unit": "°C",
                "display_order": 10
            },
            "humidity_pct": {
                "label": "Indoor humidity",
                "unit": "%",
                "display_order": 20
            },
            "pressure_hpa": {
                "label": "Indoor pressure",
                "unit": "hPa",
                "display_order": 30
            }
        }
        measurements_by_time = {}

        for row in measurement_rows:
            key = row["key"]
            indoor_metrics[key] = {
                "label": row["label"],
                "unit": row["unit"],
                "display_order": row["display_order"]
            }
            measurements_by_time.setdefault(row["reading_time"], {})[key] = row["value"]

        weather = [dict(row) for row in weather_rows]
        weather_times = [
            datetime.fromisoformat(row["observed_ts"])
            for row in weather
        ]
        observations = []

        for row in indoor_rows:
            reading_time = datetime.fromisoformat(row["reading_time"])
            insertion_point = bisect_left(weather_times, reading_time)
            candidate_indexes = (
                insertion_point - 1,
                insertion_point
            )
            nearest = min(
                (
                    weather[index]
                    for index in candidate_indexes
                    if 0 <= index < len(weather)
                ),
                key=lambda item: abs(
                    datetime.fromisoformat(item["observed_ts"]) - reading_time
                ),
                default=None
            )
            outdoor = None

            if nearest is not None and abs(
                datetime.fromisoformat(nearest["observed_ts"]) - reading_time
            ).total_seconds() <= 1800:
                outdoor = {
                    key: nearest[key]
                    for key in (
                        "temperature_c",
                        "humidity_pct",
                        "dew_point_c",
                        "pressure_hpa",
                        "precipitation_mm",
                        "wind_speed_kmh",
                        "cloud_cover_pct"
                    )
                }

            indoor = {
                "temperature_c": row["temperature_c"],
                "humidity_pct": row["humidity_pct"],
                "pressure_hpa": row["pressure_hpa"]
            }
            indoor.update(measurements_by_time.get(row["reading_time"], {}))
            observations.append({
                "reading_time": row["reading_time"],
                "indoor": indoor,
                "outdoor": outdoor
            })

        return {
            "observations": observations,
            "indoor_metrics": indoor_metrics,
            "sensor_bucket_count": len(indoor_rows),
            "aligned_bucket_count": sum(
                observation["outdoor"] is not None
                for observation in observations
            )
        }

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = PROJECT_DIR / "data" / "climatecube.db"
API_URL = "https://api.open-meteo.com/v1/forecast"
PROVIDER = "Open-Meteo"
COLLECTION_INTERVAL_SEC = 900
DAYLIGHT_HISTORY_DAYS = 92
DAYLIGHT_FORECAST_DAYS = 7
CURRENT_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "surface_pressure",
    "precipitation",
    "wind_speed_10m",
    "cloud_cover",
    "weather_code"
)


def get_connection():
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema():
    with get_connection() as connection:
        connection.executescript(
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

            CREATE TABLE IF NOT EXISTS weather_daylight (
                daylight_id INTEGER PRIMARY KEY AUTOINCREMENT,
                day DATE NOT NULL,
                sunrise_ts DATETIME NOT NULL,
                sunset_ts DATETIME NOT NULL,
                insert_ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                provider TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                UNIQUE(provider, day, latitude, longitude)
            );

            CREATE INDEX IF NOT EXISTS idx_weather_daylight_day
            ON weather_daylight(day);

            CREATE TABLE IF NOT EXISTS app_setting (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL
            );
            """
        )


def get_location():
    with get_connection() as connection:
        settings = {
            row["setting_key"]: row["setting_value"]
            for row in connection.execute(
                """
                SELECT setting_key, setting_value
                FROM app_setting
                WHERE setting_key IN (
                    'weather_latitude',
                    'weather_longitude',
                    'weather_location_name'
                )
                """
            )
        }

    latitude = settings.get("weather_latitude") or os.environ.get(
        "CLIMATECUBE_WEATHER_LATITUDE"
    )
    longitude = settings.get("weather_longitude") or os.environ.get(
        "CLIMATECUBE_WEATHER_LONGITUDE"
    )

    if latitude is None or longitude is None:
        return None

    return {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "name": settings.get("weather_location_name", "Outdoor Weather")
    }


def daylight_backfill_needed(location):
    ensure_schema()
    target_day = (
        datetime.now(timezone.utc).date()
        - timedelta(days=DAYLIGHT_HISTORY_DAYS - 2)
    ).isoformat()

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT MIN(day) AS earliest_day
            FROM weather_daylight
            WHERE provider = ?
              AND ABS(latitude - ?) < 0.1
              AND ABS(longitude - ?) < 0.1
            """,
            (
                PROVIDER,
                location["latitude"],
                location["longitude"]
            )
        ).fetchone()

    return row["earliest_day"] is None or row["earliest_day"] > target_day


def build_api_url(location, daylight_history_days=1):
    parameters = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": ",".join(CURRENT_FIELDS),
        "daily": "sunrise,sunset",
        "past_days": daylight_history_days,
        "forecast_days": DAYLIGHT_FORECAST_DAYS,
        "timeformat": "unixtime",
        "timezone": "GMT"
    }
    return f"{API_URL}?{urlencode(parameters)}"


def _format_utc_timestamp(timestamp):
    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S")


def parse_weather_payload(payload, location):
    latitude = float(payload.get("latitude", location["latitude"]))
    longitude = float(payload.get("longitude", location["longitude"]))
    current = payload["current"]
    daily = payload["daily"]
    daylight = []
    daily_lengths = {
        len(daily[field])
        for field in ("time", "sunrise", "sunset")
    }
    if len(daily_lengths) != 1:
        raise ValueError("Open-Meteo returned mismatched daylight arrays")

    for day, sunrise, sunset in zip(
        daily["time"],
        daily["sunrise"],
        daily["sunset"]
    ):
        daylight.append({
            "day": datetime.fromtimestamp(
                day,
                tz=timezone.utc
            ).date().isoformat(),
            "sunrise_ts": _format_utc_timestamp(sunrise),
            "sunset_ts": _format_utc_timestamp(sunset),
            "latitude": latitude,
            "longitude": longitude
        })

    observation = {
        "observed_ts": _format_utc_timestamp(current["time"]),
        "latitude": latitude,
        "longitude": longitude,
        "temperature_c": float(current["temperature_2m"]),
        "humidity_pct": float(current["relative_humidity_2m"]),
        "dew_point_c": current.get("dew_point_2m"),
        "pressure_hpa": current.get("surface_pressure"),
        "precipitation_mm": current.get("precipitation"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "cloud_cover_pct": current.get("cloud_cover"),
        "weather_code": current.get("weather_code")
    }
    return observation, daylight


def fetch_current_weather(location, daylight_history_days=1):
    with urlopen(
        build_api_url(location, daylight_history_days),
        timeout=20
    ) as response:
        payload = json.load(response)

    return parse_weather_payload(payload, location)


def store_weather(observation, daylight):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO weather_observation (
                observed_ts,
                provider,
                latitude,
                longitude,
                temperature_c,
                humidity_pct,
                dew_point_c,
                pressure_hpa,
                precipitation_mm,
                wind_speed_kmh,
                cloud_cover_pct,
                weather_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, observed_ts, latitude, longitude)
            DO UPDATE SET
                temperature_c = excluded.temperature_c,
                humidity_pct = excluded.humidity_pct,
                dew_point_c = excluded.dew_point_c,
                pressure_hpa = excluded.pressure_hpa,
                precipitation_mm = excluded.precipitation_mm,
                wind_speed_kmh = excluded.wind_speed_kmh,
                cloud_cover_pct = excluded.cloud_cover_pct,
                weather_code = excluded.weather_code,
                insert_ts = CURRENT_TIMESTAMP
            """,
            (
                observation["observed_ts"],
                PROVIDER,
                observation["latitude"],
                observation["longitude"],
                observation["temperature_c"],
                observation["humidity_pct"],
                observation["dew_point_c"],
                observation["pressure_hpa"],
                observation["precipitation_mm"],
                observation["wind_speed_kmh"],
                observation["cloud_cover_pct"],
                observation["weather_code"]
            )
        )
        connection.executemany(
            """
            INSERT INTO weather_daylight (
                day,
                sunrise_ts,
                sunset_ts,
                provider,
                latitude,
                longitude
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, day, latitude, longitude)
            DO UPDATE SET
                sunrise_ts = excluded.sunrise_ts,
                sunset_ts = excluded.sunset_ts,
                insert_ts = CURRENT_TIMESTAMP
            """,
            [
                (
                    day["day"],
                    day["sunrise_ts"],
                    day["sunset_ts"],
                    PROVIDER,
                    day["latitude"],
                    day["longitude"]
                )
                for day in daylight
            ]
        )


def store_observation(observation):
    store_weather(observation, [])


def collect_once():
    location = get_location()

    if location is None:
        return False

    history_days = (
        DAYLIGHT_HISTORY_DAYS
        if daylight_backfill_needed(location)
        else 1
    )
    observation, daylight = fetch_current_weather(location, history_days)
    store_weather(observation, daylight)
    print(
        f"Stored outdoor weather for {observation['observed_ts']} UTC "
        f"and {len(daylight)} daylight records",
        flush=True
    )
    return True


def main():
    ensure_schema()
    waiting_for_location = False

    while True:
        sleep_seconds = COLLECTION_INTERVAL_SEC

        try:
            collected = collect_once()

            if not collected and not waiting_for_location:
                print(
                    "Weather collection is waiting for a location in Settings.",
                    flush=True
                )
                waiting_for_location = True
            if not collected:
                sleep_seconds = 60
            elif collected:
                waiting_for_location = False
        except (HTTPError, URLError, TimeoutError, KeyError, TypeError, ValueError) as error:
            print(f"Weather collection failed: {error}", flush=True)
        except sqlite3.Error as error:
            print(f"Weather database error: {error}", flush=True)

        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
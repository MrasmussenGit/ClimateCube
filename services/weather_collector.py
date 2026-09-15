import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = PROJECT_DIR / "data" / "climatecube.db"
API_URL = "https://api.open-meteo.com/v1/forecast"
PROVIDER = "Open-Meteo"
COLLECTION_INTERVAL_SEC = 900
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


def build_api_url(location):
    parameters = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": ",".join(CURRENT_FIELDS),
        "timeformat": "unixtime",
        "timezone": "GMT"
    }
    return f"{API_URL}?{urlencode(parameters)}"


def fetch_current_weather(location):
    with urlopen(build_api_url(location), timeout=20) as response:
        payload = json.load(response)

    current = payload["current"]
    observed_ts = datetime.fromtimestamp(
        current["time"],
        tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "observed_ts": observed_ts,
        "latitude": float(payload.get("latitude", location["latitude"])),
        "longitude": float(payload.get("longitude", location["longitude"])),
        "temperature_c": float(current["temperature_2m"]),
        "humidity_pct": float(current["relative_humidity_2m"]),
        "dew_point_c": current.get("dew_point_2m"),
        "pressure_hpa": current.get("surface_pressure"),
        "precipitation_mm": current.get("precipitation"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "cloud_cover_pct": current.get("cloud_cover"),
        "weather_code": current.get("weather_code")
    }


def store_observation(observation):
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


def collect_once():
    location = get_location()

    if location is None:
        return False

    observation = fetch_current_weather(location)
    store_observation(observation)
    print(
        f"Stored outdoor weather for {observation['observed_ts']} UTC",
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
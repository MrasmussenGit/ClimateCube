-- ==========================================
-- ClimateCube Database
-- ==========================================

PRAGMA foreign_keys = ON;

-- ==========================================
-- Room
-- ==========================================

CREATE TABLE room (
    room_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    room_name   TEXT NOT NULL UNIQUE,
    description TEXT
);

-- ==========================================
-- Sensor
-- ==========================================

CREATE TABLE sensor (
    sensor_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id      TEXT NOT NULL UNIQUE,
    sensor_name    TEXT NOT NULL,
    sensor_type    TEXT NOT NULL,
    install_date   TEXT,
    ip_address     TEXT,
    active_flag    INTEGER NOT NULL DEFAULT 1,
    first_seen_ts  TEXT,
    reading_interval_sec INTEGER,
    hardware_json  TEXT
);

-- ==========================================
-- Room Assignment
-- Keeps history of sensor location changes
-- ==========================================

CREATE TABLE room_assignment (
    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id     INTEGER NOT NULL,
    room_id       INTEGER NOT NULL,
    assigned_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (sensor_id)
        REFERENCES sensor(sensor_id),

    FOREIGN KEY (room_id)
        REFERENCES room(room_id)
);

-- ==========================================
-- Sensor Readings
-- ==========================================

CREATE TABLE sensor_reading (
    reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id INTEGER NOT NULL,

    pico_ts DATETIME,
    insert_ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    temperature_c REAL NOT NULL,
    humidity_pct REAL NOT NULL,
    pressure_hpa REAL NOT NULL,
    gas_resistance_ohms INTEGER,

    FOREIGN KEY (sensor_id)
        REFERENCES sensor(sensor_id)
);

-- ==========================================
-- Indexes
-- ==========================================

CREATE INDEX idx_sensor_reading_sensor_time
ON sensor_reading(sensor_id, pico_ts);

-- ==========================================
-- Extensible Measurements
-- ==========================================

CREATE TABLE measurement_definition (
    measurement_key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    unit TEXT NOT NULL,
    precision_digits INTEGER NOT NULL DEFAULT 2,
    display_format TEXT NOT NULL DEFAULT 'number',
    display_order INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE sensor_measurement (
    reading_id INTEGER NOT NULL,
    measurement_key TEXT NOT NULL,
    measurement_value REAL NOT NULL,

    PRIMARY KEY (reading_id, measurement_key),
    FOREIGN KEY (reading_id)
        REFERENCES sensor_reading(reading_id) ON DELETE CASCADE,
    FOREIGN KEY (measurement_key)
        REFERENCES measurement_definition(measurement_key)
);

CREATE INDEX idx_sensor_measurement_key_reading
ON sensor_measurement(measurement_key, reading_id);

-- ==========================================
-- Outdoor Weather
-- ==========================================

CREATE TABLE weather_observation (
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

CREATE INDEX idx_weather_observation_time
ON weather_observation(observed_ts);

CREATE TABLE app_setting (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL
);
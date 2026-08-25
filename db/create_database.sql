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
    sensor_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id     TEXT NOT NULL UNIQUE,
    sensor_name   TEXT NOT NULL,
    sensor_type   TEXT NOT NULL,
    install_date  TEXT,
    active_flag   INTEGER NOT NULL DEFAULT 1
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
    reading_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id      INTEGER NOT NULL,
    reading_ts     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    temperature_c REAL NOT NULL,
    humidity_pct  REAL NOT NULL,
    pressure_hpa  REAL NOT NULL,

    FOREIGN KEY (sensor_id)
        REFERENCES sensor(sensor_id)
);

-- ==========================================
-- Indexes
-- ==========================================

CREATE INDEX idx_sensor_reading_sensor_time
ON sensor_reading(sensor_id, reading_ts);
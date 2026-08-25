INSERT INTO room (room_name, description)
VALUES
('Living Room', 'Main living area');

INSERT INTO sensor (
    device_id,
    sensor_name,
    sensor_type
)
VALUES (
    'CC-001',
    'ClimateCube #1',
    'BME280'
);

INSERT INTO room_assignment (
    sensor_id,
    room_id
)
VALUES (
    1,
    1
);
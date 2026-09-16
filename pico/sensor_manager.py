import gas_sensor
import sensor as environment_sensor


OPTIONAL_DRIVERS = (gas_sensor,)


def read():
    environmental = environment_sensor.GetTempData()
    if environmental is None:
        return None

    hardware = environment_sensor.get_hardware()
    measurements = environment_sensor.get_measurements(environmental)

    for driver in OPTIONAL_DRIVERS:
        result = driver.read()
        if result is None:
            continue
        hardware.extend(result["hardware"])
        measurements.extend(result["measurements"])

    return {
        "environmental": environmental,
        "hardware": hardware,
        "measurements": measurements
    }
from machine import Pin, I2C
import bme280_float
import bme680

bme = None
sensor_type = None
last_error = None

BME688_CHIP_ID = 0x61
CHIP_ID_REGISTER = 0xD0


def init():
    global bme, sensor_type, last_error

    bme = None
    sensor_type = None
    stage = "I2C setup/scan"

    try:
        i2c = I2C(0, scl=Pin(5), sda=Pin(4))
        addresses = i2c.scan()

        if 0x76 in addresses:
            address = 0x76
        elif 0x77 in addresses:
            address = 0x77
        else:
            last_error = "No environmental sensor at 0x76/0x77; I2C addresses: {}".format(
                ", ".join("0x{:02x}".format(value) for value in addresses) or "none"
            )
            return False

        stage = "Sensor initialization at 0x{:02x}".format(address)
        chip_id = i2c.readfrom_mem(address, CHIP_ID_REGISTER, 1)[0]

        if chip_id == BME688_CHIP_ID:
            bme = bme680.BME680_I2C(i2c, address=address)
            sensor_type = "BME688"
        else:
            bme = bme280_float.BME280(i2c=i2c, address=address)
            sensor_type = "BME280"

        last_error = None
        return True
    except (OSError, RuntimeError) as error:
        last_error = "{} failed: {}".format(stage, error)
        bme = None
        sensor_type = None
        return False


def get_error():
    return last_error


def get_sensor_type():
    return sensor_type


def get_hardware():
    return [sensor_type] if sensor_type else []


def get_measurements(data):
    measurements = [
        {
            "key": "temperature_c",
            "label": "Temperature",
            "value": data["temperature_c"],
            "unit": "°C",
            "precision": 2,
            "format": "temperature",
            "order": 10
        },
        {
            "key": "humidity_pct",
            "label": "Humidity",
            "value": data["humidity_pct"],
            "unit": "%",
            "precision": 2,
            "format": "number",
            "order": 20
        },
        {
            "key": "pressure_hpa",
            "label": "Pressure",
            "value": data["pressure_hpa"],
            "unit": "hPa",
            "precision": 2,
            "format": "number",
            "order": 30
        }
    ]

    if data.get("gas_resistance_ohms") is not None:
        measurements.append({
            "key": "bme688_gas_resistance_ohms",
            "label": "BME688 gas resistance",
            "value": data["gas_resistance_ohms"],
            "unit": "Ω",
            "precision": 2,
            "format": "resistance",
            "order": 40
        })

    return measurements

def GetTempData():
    global bme, sensor_type, last_error

    if bme is None and not init():
        return None

    try:
        if sensor_type == "BME688":
            data = {
                "temperature_c": float(bme.temperature),
                "pressure_hpa": float(bme.pressure),
                "humidity_pct": float(bme.humidity),
                "gas_resistance_ohms": int(bme.gas)
            }
            last_error = None
            return data

        temp, pressure, humidity = bme.values
    except (OSError, RuntimeError) as error:
        last_error = "{} reading failed: {}".format(sensor_type, error)
        bme = None
        sensor_type = None
        return None

    last_error = None
    return {
        "temperature_c": float(temp.replace("C", "")),
        "pressure_hpa": float(pressure.replace("hPa", "")),
        "humidity_pct": float(humidity.replace("%", "")),
        "gas_resistance_ohms": None
}
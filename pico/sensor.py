from machine import Pin, I2C
import bme280_float
import bme680

bme = None
sensor_type = None

BME688_CHIP_ID = 0x61
CHIP_ID_REGISTER = 0xD0


def init():
    global bme, sensor_type

    i2c = I2C(0, scl=Pin(5), sda=Pin(4))
    addresses = i2c.scan()

    if 0x76 in addresses:
        address = 0x76
    elif 0x77 in addresses:
        address = 0x77
    else:
        bme = None
        sensor_type = None
        return False

    try:
        chip_id = i2c.readfrom_mem(address, CHIP_ID_REGISTER, 1)[0]

        if chip_id == BME688_CHIP_ID:
            bme = bme680.BME680_I2C(i2c, address=address)
            sensor_type = "BME688"
        else:
            bme = bme280_float.BME280(i2c=i2c, address=address)
            sensor_type = "BME280"

        return True
    except (OSError, RuntimeError):
        bme = None
        sensor_type = None
        return False


def get_sensor_type():
    return sensor_type

def GetTempData():
    global bme, sensor_type

    if bme is None and not init():
        return None

    try:
        if sensor_type == "BME688":
            return {
                "temperature_c": float(bme.temperature),
                "pressure_hpa": float(bme.pressure),
                "humidity_pct": float(bme.humidity),
                "gas_resistance_ohms": int(bme.gas)
            }

        temp, pressure, humidity = bme.values
    except (OSError, RuntimeError):
        bme = None
        sensor_type = None
        return None

    return {
        "temperature_c": float(temp.replace("C", "")),
        "pressure_hpa": float(pressure.replace("hPa", "")),
        "humidity_pct": float(humidity.replace("%", "")),
        "gas_resistance_ohms": None
}
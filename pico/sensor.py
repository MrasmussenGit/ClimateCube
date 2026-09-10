from machine import Pin, I2C
import bme280_float

bme = None


def init():
    global bme

    i2c = I2C(0, scl=Pin(5), sda=Pin(4))
    addresses = i2c.scan()

    if 0x76 in addresses:
        address = 0x76
    elif 0x77 in addresses:
        address = 0x77
    else:
        bme = None
        return False

    try:
        bme = bme280_float.BME280(i2c=i2c, address=address)
        return True
    except OSError:
        bme = None
        return False

def GetTempData():
    global bme

    if bme is None and not init():
        return None

    try:
        temp, pressure, humidity = bme.values
    except OSError:
        bme = None
        return None

    return {
        "temperature_c": float(temp.replace("C", "")),
        "pressure_hpa": float(pressure.replace("hPa", "")),
        "humidity_pct": float(humidity.replace("%", ""))
}
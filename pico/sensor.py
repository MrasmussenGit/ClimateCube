from machine import Pin, I2C
import bme280

v
bme = bme280.BME280(i2c=i2c, address=0x76)

def GetTempData():
    c = float(bme.temperature.replace("C", ""))
    f = c * 9 / 5 + 32


    c = float(bme.temperature.replace("C", ""))

    return {
        "temperature_c": round(c, 1),
        "pressure_hpa": float(bme.pressure.replace("hPa", "")),
        "humidity_pct": float(bme.humidity.replace("%", ""))
    }

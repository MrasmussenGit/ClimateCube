from machine import Pin, I2C
import bme280_float

i2c = I2C(0, scl=Pin(5), sda=Pin(4))
bme = bme280_float.BME280(i2c=i2c, address=0x76)

def GetTempData():
    temp, pressure, humidity = bme.values

    return {
        "temperature_c": float(temp.replace("C", "")),
        "pressure_hpa": float(pressure.replace("hPa", "")),
        "humidity_pct": float(humidity.replace("%", ""))
}
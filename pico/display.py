from machine import Pin, I2C
from ssd1306 import SSD1306_I2C
import device

oled = None
page = 0


def init():
    global oled

    i2c = I2C(0, scl=Pin(5), sda=Pin(4))

    oled = SSD1306_I2C(128, 64, i2c)

    oled.fill(0)
    oled.text("ClimateCube", 0, 0)
    oled.text("Starting...", 0, 15)
    oled.show()


def update(data, dt):

    temp_c = data["temperature_c"]
    temp_f = (temp_c * 9 / 5) + 32

    humidity = data["humidity_pct"]
    pressure = data["pressure_hpa"]

    hour = (dt[4] - 4) % 24
    minute = dt[5]

    oled.fill(0)

    # Top row
    oled.text(
        device.get_display_id(),
        0,
        0
    )

    oled.text(
        "{:02}:{:02}".format(hour, minute),
        82,
        0
    )

    # Readings
    oled.text("T: {:.1f}F".format(temp_f), 0, 18)
    oled.text("H: {:.1f}%".format(humidity), 0, 34)
    oled.text("P: {:.0f}".format(pressure), 0, 50)

    oled.show()


def show_temperature(data):

    temp_c = data["temperature_c"]
    temp_f = (temp_c * 9 / 5) + 32

    oled.fill(0)

    oled.text("Temperature", 0, 0)
    oled.text("{:.1f} F".format(temp_f), 0, 24)

    oled.show()


def show_humidity(data):

    oled.fill(0)

    oled.text("Humidity", 0, 0)
    oled.text(
        "{:.1f}%".format(
            data["humidity_pct"]
        ),
        0,
        24
    )

    oled.show()


def show_pressure(data):

    oled.fill(0)

    oled.text("Pressure", 0, 0)
    oled.text(
        "{:.1f}".format(
            data["pressure_hpa"]
        ),
        0,
        24
    )

    oled.show()
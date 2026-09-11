from machine import Pin, I2C
from ssd1306 import SSD1306_I2C
import device
import time

oled = None
page = 0


def init():
    global oled

    i2c = I2C(0, scl=Pin(5), sda=Pin(4))

    if 0x3c not in i2c.scan():
        oled = None
        return False

    try:
        oled = SSD1306_I2C(128, 64, i2c)

        oled.fill(0)
        oled.text("ClimateCube", 0, 0)
        oled.text("Starting...", 0, 15)
        oled.show()
        return True
    except OSError:
        oled = None
        return False


def _ready():
    return oled is not None or init()


def is_available():
    return oled is not None


def _show(draw):
    global oled

    if not _ready():
        return False

    try:
        oled.fill(0)
        draw()
        oled.show()
        return True
    except OSError:
        oled = None
        return False


SEGMENTS = {
    "0": "abcedf",
    "1": "bc",
    "2": "abdeg",
    "3": "abcdg",
    "4": "bcfg",
    "5": "acdfg",
    "6": "acdefg",
    "7": "abc",
    "8": "abcdefg",
    "9": "abcdfg"
}


def _draw_segment_digit(x, y, digit):
    segments = SEGMENTS.get(digit, "")
    lines = {
        "a": (x + 2, y, x + 10, y),
        "b": (x + 12, y + 2, x + 12, y + 12),
        "c": (x + 12, y + 16, x + 12, y + 26),
        "d": (x + 2, y + 28, x + 10, y + 28),
        "e": (x, y + 16, x, y + 26),
        "f": (x, y + 2, x, y + 12),
        "g": (x + 2, y + 14, x + 10, y + 14)
    }

    for segment in segments:
        x1, y1, x2, y2 = lines[segment]
        oled.line(x1, y1, x2, y2, 1)
        if y1 == y2:
            oled.line(x1, y1 + 1, x2, y2 + 1, 1)
        else:
            oled.line(x1 + 1, y1, x2 + 1, y2, 1)


def _draw_large_temperature(temp_f):
    text = "{:.1f}".format(temp_f)
    number_width = sum(6 if character == "." else 17 for character in text)
    suffix_width = 17
    x = max(0, (128 - number_width - suffix_width) // 2)

    for character in text:
        if character == ".":
            oled.fill_rect(x, 40, 3, 3, 1)
            x += 6
        else:
            _draw_segment_digit(x, 13, character)
            x += 17

    oled.ellipse(x + 1, 14, 2, 2, 1)
    oled.text("F", x + 7, 23)


def _format_countdown(seconds_remaining):
    seconds_remaining = max(0, int(seconds_remaining))

    if seconds_remaining >= 360000:
        return "99h+"

    if seconds_remaining >= 3600:
        hours = seconds_remaining // 3600
        minutes = (seconds_remaining % 3600) // 60
        return "{}h{:02}".format(hours, minutes)

    minutes = seconds_remaining // 60
    seconds = seconds_remaining % 60
    return "{:02}:{:02}".format(minutes, seconds)


def update(data, dt, seconds_remaining=None):
    temp_c = data["temperature_c"]
    temp_f = (temp_c * 9 / 5) + 32

    humidity = data["humidity_pct"]
    pressure = data["pressure_hpa"]

    def draw():
        oled.text(device.get_display_id(), 0, 0)
        if seconds_remaining is not None:
            countdown = _format_countdown(seconds_remaining)
            oled.text(countdown, 128 - (len(countdown) * 8), 0)
        _draw_large_temperature(temp_f)
        oled.text("H:{:.0f}%".format(humidity), 0, 54)
        oled.text("P:{:.0f}".format(pressure), 72, 54)

    return _show(draw)


def show_publish_success():
    global oled

    if not _ready():
        return False

    try:
        frames = (0, 1, 2)

        for frame in frames:
            oled.fill(0)
            oled.text("READING SENT", 16, 5)
            oled.line(43, 34, 54, 45, 1)
            oled.line(54, 45, 78, 21, 1)
            oled.line(43, 35, 54, 46, 1)
            oled.line(54, 46, 78, 22, 1)

            if frame >= 1:
                oled.line(35, 26, 29, 22, 1)
                oled.line(86, 26, 92, 22, 1)
            if frame >= 2:
                oled.line(35, 42, 28, 46, 1)
                oled.line(86, 42, 93, 46, 1)

            oled.show()
            time.sleep_ms(140)

        time.sleep_ms(300)
        return True
    except OSError:
        oled = None
        return False


def show_sensor_not_detected():
    def draw():
        oled.text("ClimateCube", 0, 0)
        oled.text("Sensor not", 0, 22)
        oled.text("detected", 0, 38)

    return _show(draw)


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
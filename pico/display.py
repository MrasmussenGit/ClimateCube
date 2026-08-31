from machine import Pin, I2C
from ssd1306 import SSD1306_I2C

oled = None


def init():
    global oled

    i2c = I2C(0, scl=Pin(5), sda=Pin(4))

    oled = SSD1306_I2C(128, 64, i2c)

    oled.fill(0)
    oled.text("ClimateCube", 0, 0)
    oled.text("Starting...", 0, 15)
    oled.show()


#def update(temp_f, humidity, pressure):

    #oled.fill(0)

    #oled.text("ClimateCube", 0, 0)

    #oled.text("Temp:", 0, 18)
    #oled.text(f"{temp_f:.1f}F", 60, 18)

    #oled.text("Hum:", 0, 34)
    #oled.text(f"{humidity:.1f}%", 60, 34)

    #oled.text("Pres:", 0, 50)
    #oled.text(f"{pressure:.1f}", 40, 50)

    #oled.show()
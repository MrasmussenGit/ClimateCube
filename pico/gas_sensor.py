from machine import I2C, Pin

from mics6814 import MICS6814


sensor = None


def init():
    global sensor

    try:
        sensor = MICS6814(I2C(0, scl=Pin(5), sda=Pin(4)))
        return True
    except (OSError, RuntimeError):
        sensor = None
        return False


def read():
    global sensor

    if sensor is None and not init():
        return None

    try:
        values = sensor.read()
    except (OSError, RuntimeError):
        sensor = None
        return None

    return {
        "hardware": ["MICS6814"],
        "measurements": [
            {
                "key": "mics6814_reducing_ohms",
                "label": "Reducing gases",
                "value": values["reducing_ohms"],
                "unit": "Ω",
                "precision": 2,
                "format": "resistance",
                "order": 50
            },
            {
                "key": "mics6814_oxidising_ohms",
                "label": "Oxidising gases",
                "value": values["oxidising_ohms"],
                "unit": "Ω",
                "precision": 2,
                "format": "resistance",
                "order": 60
            },
            {
                "key": "mics6814_nh3_ohms",
                "label": "NH3 gases",
                "value": values["nh3_ohms"],
                "unit": "Ω",
                "precision": 2,
                "format": "resistance",
                "order": 70
            }
        ]
    }
import machine
import ubinascii


def get_device_id():
    return ubinascii.hexlify(
        machine.unique_id()
    ).decode()


def get_display_id():
    return get_device_id()[-6:].upper()
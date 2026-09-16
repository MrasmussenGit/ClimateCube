from machine import Pin
import time


ENCODER_A_PIN = 10
ENCODER_B_PIN = 11
BUTTON_PIN = 12
BUTTON_DEBOUNCE_MS = 40

_TRANSITIONS = (
    0, -1, 1, 0,
    1, 0, 0, -1,
    -1, 0, 0, 1,
    0, 1, -1, 0
)

encoder_a = None
encoder_b = None
button = None
last_encoder_state = 0
encoder_accumulator = 0
button_observed = 1
button_stable = 1
button_changed_at = 0


def init():
    global encoder_a, encoder_b, button
    global last_encoder_state, encoder_accumulator
    global button_observed, button_stable, button_changed_at

    encoder_a = Pin(ENCODER_A_PIN, Pin.IN, Pin.PULL_UP)
    encoder_b = Pin(ENCODER_B_PIN, Pin.IN, Pin.PULL_UP)
    button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
    last_encoder_state = (encoder_a.value() << 1) | encoder_b.value()
    encoder_accumulator = 0
    button_observed = button.value()
    button_stable = button_observed
    button_changed_at = time.ticks_ms()


def poll():
    global last_encoder_state, encoder_accumulator
    global button_observed, button_stable, button_changed_at

    if encoder_a is None:
        init()

    rotation = 0
    encoder_state = (encoder_a.value() << 1) | encoder_b.value()
    if encoder_state != last_encoder_state:
        transition = (last_encoder_state << 2) | encoder_state
        encoder_accumulator += _TRANSITIONS[transition]
        last_encoder_state = encoder_state

        if encoder_accumulator >= 4:
            rotation = 1
            encoder_accumulator = 0
        elif encoder_accumulator <= -4:
            rotation = -1
            encoder_accumulator = 0

    pressed = False
    now = time.ticks_ms()
    button_value = button.value()
    if button_value != button_observed:
        button_observed = button_value
        button_changed_at = now
    elif (
        button_value != button_stable and
        time.ticks_diff(now, button_changed_at) >= BUTTON_DEBOUNCE_MS
    ):
        button_stable = button_value
        pressed = button_stable == 0

    return rotation, pressed
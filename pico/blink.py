from machine import Pin
from time import sleep

led = Pin("LED", Pin.OUT)

print("Hello from Pico")

while True:
    led.toggle()
    sleep(0.5)
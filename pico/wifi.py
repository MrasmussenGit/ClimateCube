import network
import time

SSID = "RangerTown"
PASSWORD = "************"


def connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]

        if ip != "0.0.0.0":
            print("Already connected")
            print("IP Address:", ip)
            return wlan

    print("Connecting to WiFi...")
    wlan.connect(SSID, PASSWORD)

    timeout = 15

    while timeout > 0:
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]

            if ip != "0.0.0.0":
                break

        print(".", end="")
        timeout -= 1
        time.sleep(1)

    print()

    if not wlan.isconnected():
        print("WiFi connection failed")
        return None

    print("WiFi associated")
    print("Waiting for DHCP...")

    dhcp_timeout = 10

    while dhcp_timeout > 0:
        ip = wlan.ifconfig()[0]

        if ip != "0.0.0.0":
            break

        print(".", end="")
        dhcp_timeout -= 1
        time.sleep(1)

    print()

    ip = wlan.ifconfig()[0]

    if ip == "0.0.0.0":
        print("DHCP failed")
        return None

    print("Connected!")
    print("IP Address:", ip)
    print("Network Config:", wlan.ifconfig())

    return wlan
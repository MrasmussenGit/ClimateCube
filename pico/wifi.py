import network
import time

SSID = "RangerTown"
PASSWORD = "YOUR_PASSWORD"


def log(msg):
    print(msg)

    try:
        with open("boot.log", "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    log("--------------------------------")
    log("WiFi Startup")
    log("--------------------------------")

    # Already connected?
    if wlan.isconnected():
        ip = wlan.ifconfig()[0]

        if ip != "0.0.0.0":
            log("Already connected")
            log("IP Address: {}".format(ip))
            return wlan

    log("Connecting to WiFi...")
    wlan.connect(SSID, PASSWORD)

    timeout = 15

    while timeout > 0:
        if wlan.isconnected():
            break

        log("Waiting for WiFi...")
        timeout -= 1
        time.sleep(1)

    if not wlan.isconnected():
        log("WiFi connection failed")
        return None

    log("WiFi associated")

    # Wait for DHCP
    log("Waiting for DHCP lease...")

    dhcp_timeout = 15

    while dhcp_timeout > 0:
        ip = wlan.ifconfig()[0]

        if ip != "0.0.0.0":
            break

        log("Waiting for DHCP...")
        dhcp_timeout -= 1
        time.sleep(1)

    ip = wlan.ifconfig()[0]

    if ip == "0.0.0.0":
        log("DHCP failed")
        return None

    log("Connected!")
    log("IP Address: {}".format(ip))
    log("Network Config: {}".format(wlan.ifconfig()))

    return wlan
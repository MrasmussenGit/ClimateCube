import network
import time

SSID = "changeme"
PASSWORD = "changeme"


def log(msg):
    print(msg)

    try:
        with open("boot.log", "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def connect():

    wlan = network.WLAN(network.STA_IF)

    log("----------------------------")
    log("WiFi Startup")
    log("----------------------------")

    wlan.active(True)

    # Already connected?
    if wlan.isconnected():
        ip = wlan.ifconfig()[0]

        if ip != "0.0.0.0":
            log("Already connected")
            log("IP Address: {}".format(ip))
            return wlan

    max_attempts = 5

    for attempt in range(max_attempts):

        log("----------------------------")
        log("WiFi connection attempt {}".format(attempt + 1))
        log("----------------------------")

        try:
            wlan.disconnect()
        except Exception:
            pass

        # Reset radio between attempts
        wlan.active(False)
        time.sleep(2)

        wlan.active(True)
        time.sleep(2)

        log("Connecting to WiFi...")
        wlan.connect(SSID, PASSWORD)

        timeout = 15

        while timeout > 0:

            if wlan.isconnected():
                break

            log("Waiting for WiFi...")
            timeout -= 1
            time.sleep(1)

        if wlan.isconnected():

            log("WiFi associated")

            log("Waiting for DHCP lease...")

            dhcp_timeout = 30

            while dhcp_timeout > 0:

                ip = wlan.ifconfig()[0]

                log("Current IP: {}".format(ip))

                if ip != "0.0.0.0":
                    break

                log("Waiting for DHCP...")
                dhcp_timeout -= 1
                time.sleep(1)

            ip = wlan.ifconfig()[0]

            if ip != "0.0.0.0":

                log("Connected!")
                log("IP Address: {}".format(ip))
                log("Network Config: {}".format(wlan.ifconfig()))

                return wlan

            log("DHCP failed")

        log("WiFi Status: {}".format(wlan.status()))
        log("WiFi connection attempt failed")

        time.sleep(5)

    log("WiFi connection failed")

    return None
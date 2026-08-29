import ntptime
import time

def sync_time():
    try:
        log("Syncing time...")

        ntptime.settime()

        log("Time synced")

        return True

    except Exception as e:
        log("NTP sync failed: {}".format(e))
        return False
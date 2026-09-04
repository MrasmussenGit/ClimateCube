import ntptime
import time

def sync_time():
    try:
        print("Syncing time...")

        ntptime.settime()

        print("Time synced")

        return True

    except Exception as e:
        print("NTP sync failed: {}".format(e))
        return False
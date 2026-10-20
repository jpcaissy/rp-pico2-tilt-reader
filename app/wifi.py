import network
import time

import config

SSID = config.SSID
PASSWORD = config.PASSWORD

ERRORS = {
    network.STAT_WRONG_PASSWORD: "Wrong password",
    network.STAT_NO_AP_FOUND: "AP not found",
    network.STAT_CONNECT_FAIL: "Connect failed",
}
TIMEOUT_MS = 9_000
CONNECTION_TIMEOUT_MS = 30_000


class Wifi:
    IDLE = 0
    CONNECTING = 1
    CONNECTED = 2
    WAITING = 3

    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.last_status = Wifi.IDLE
        self.timestamp = time.ticks_ms()
        self.last_error = None

    def connect(self):
        self.last_error = None
        self.last_status = Wifi.CONNECTING
        self.timestamp = time.ticks_ms()
        self.wlan.connect(SSID, PASSWORD)

    def poll(self):
        if self.last_status == Wifi.IDLE:
            return

        now = time.ticks_ms()
        if self.last_status == Wifi.CONNECTING:
            wlan_status = self.wlan.status()

            if self.wlan.isconnected():
                self.last_status = Wifi.CONNECTED
                self.last_error = None
            elif wlan_status in ERRORS:
                # Fail fast, no need to wait for timeout
                self.fail(ERRORS[wlan_status])
            elif time.ticks_diff(now, self.timestamp) > CONNECTION_TIMEOUT_MS:
                self.fail("Timeout")
        elif self.last_status == Wifi.CONNECTED:
            # Did we lose connection?
            if not self.wlan.isconnected():
                self.last_error = "Connection lost"
                self.connect()
        elif self.last_status == Wifi.WAITING:
            if time.ticks_diff(now, self.timestamp) >= TIMEOUT_MS:
                self.connect()


    def fail(self, error):
        self.last_error = error

        try:
            self.wlan.disconnect()
        except OSError:
            pass

        self.last_status = Wifi.WAITING
        self.timestamp = time.ticks_ms()

    def status(self):
        if self.wlan.isconnected():
            return "Connected", f"IP: {self.ip()}"

        if self.last_status == Wifi.IDLE:
            status = "Idle"
        elif self.last_status == Wifi.CONNECTING:
            status = "Connecting"
        elif self.last_status == Wifi.CONNECTED:
            status = "Connected"
        elif self.last_status == Wifi.WAITING:
            time_left = round((TIMEOUT_MS - (time.ticks_diff(time.ticks_ms(), self.timestamp))) / 1000)
            status = f"Waiting {time_left}s"
        else:
            status = "Unknown"

        if self.last_error:
            if self.last_error == "Timeout":
                return status, self.last_error, "Wrong password??"
            else:
                return status, self.last_error
        else:
            return status, # ensure it returns a tuple

    def connected(self):
        return self.wlan.isconnected()

    def ip(self):
        if self.connected():
            return self.wlan.ifconfig()[0]

    def rssi(self):
        if self.connected():
            try:
                rssi = "%d dBm" % self.wlan.status("rssi")
            except Exception:
                rssi = "n/a"

            return rssi

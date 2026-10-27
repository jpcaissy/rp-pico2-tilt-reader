from collections import namedtuple

import bluetooth
import struct
import time

SCAN_MS = 3_000            # Total scan window is 3 seconds
INTERVAL_SCAN_US = 500_000 # Scan every 0.5s
WINDOW_SCAN_MS = 100_000   # One scan window is 0.1s

STALE_DEVICES_MS = 300_000    # Drop device from the list after 5 minutes

_IRQ_SCAN_RESULT = 5
_IRQ_SCAN_DONE = 6

# Tilt iBeacon UUID: A495BBxx-C5B1-4B44-B512-1370F02D74DE (xx = colour code)
_HEAD = b"\xa4\x95\xbb"
_TAIL = b"\xc5\xb1\x4b\x44\xb5\x12\x13\x70\xf0\x2d\x74\xde"

COLORS = {
    0x10: "red",
    0x20: "green",
    0x30: "black",
    0x40: "purple",
    0x50: "orange",
    0x60: "blue",
    0x70: "yellow",
    0x80: "pink",
}

Beacon = namedtuple("Beacon", ["label", "type", "temperature", "gravity", "battery", "timestamp"]) # temperature is in celcius

def f_to_c(f):
    return round((f - 32) * (5/9), 1)


class Scanner:
    def __init__(self):
        self.ble = bluetooth.BLE()
        self.devices = {}
        self.scanning = False

    def start(self):
        self.ble.active(True)
        self.ble.irq(self.irq)
        self.scan()

    def scan(self):
        try:
            self.scanning = True
            self.ble.gap_scan(SCAN_MS, INTERVAL_SCAN_US, WINDOW_SCAN_MS, False)
        except OSError:
            self.scanning = False

    def parse_adv(self, adv, addr):
        b = bytes(adv)

        i = b.find(b"\x4c\x00\x02\x15") # Apple iBeacon header, used by Tilt
        if i >= 0:
            return self.parse_tilt_adv(b[i:])

        i = b.find(b"RAPT")
        if i >= 0:
            return self.parse_rapt_pill_adv(b[i:], addr)

    def parse_rapt_pill_adv(self, data, addr):
        if len(data) != 25:
            return None

        body = data[4:25]
        ver = body[0]
        try:
            if ver == 1:     # version, mac, temp, gravity, x, y, z, battery
                _v, _mac, temp_raw, gravity, _x, _y, _z, battery = struct.unpack(">B6sHfhhhh", body)
            elif ver == 2:   # version, reserved, gv_valid, gv, temp, gravity, x, y, z, battery
                _v, _r, _ok, _gv, temp_raw, gravity, _x, _y, _z, battery = struct.unpack(">BBBfHfhhhh", body)
            else:
                return None
        except Exception:
            return None

        gravity /= 1000
        # Ensure we have a valid gravity reading
        if not (0.5 < gravity < 2.0):
            return None

        label = "%02X%02X" % (addr[4], addr[5])
        beacon = Beacon(label, "pill", temp_raw / 128 - 273.15, round(gravity, 4), battery, time.ticks_ms())

        return beacon


    def parse_tilt_adv(self, data):
        if len(data) < 24:
            return None

        # Ensure it matches the expected beacon header/tail and that the color exists
        if not (data[4:7] == _HEAD and data[8:20] == _TAIL and data[7] in COLORS):
            return None

        major = (data[20] << 8) | data[21]
        minor = (data[22] << 8) | data[23]

        # TODO: parse battery age beacon
        if major == 999:
            return None

        if minor >= 5000:
            # Minor >= 5000 means tilt pro, did not test
            beacon = Beacon(COLORS[data[7]], "tilt", f_to_c(major), minor / 10_000, None)
        else:
            beacon = Beacon(COLORS[data[7]], "tilt", f_to_c(major), minor / 1000, None, time.ticks_ms())

        return beacon


    def irq(self, event, data):
        if event == _IRQ_SCAN_RESULT:
            _addr_type, addr, _adv_type, rssi, adv = data
            result = self.parse_adv(adv, addr)
            if result:
                self.devices[result.label] = result
        elif event == _IRQ_SCAN_DONE:
            self.scanning = False

    def poll(self):
        if not self.scanning:
            self.scanning = True
            now = time.ticks_ms()
            stale_devices = []
            for device in self.devices.values():
                if time.ticks_diff(now, device.timestamp) >= STALE_DEVICES_MS:
                    stale_devices.append(device.label)
            for label in stale_devices:
                del self.devices[label]

            self.scan()

    def sorted_devices(self):
        return sorted(self.devices.items())

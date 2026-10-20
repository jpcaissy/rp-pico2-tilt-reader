import bluetooth
import struct
import time

SCAN_MS = 5000          # length of one scan window
STALE_TILT_MS = 60000   # drop a Tilt not heard from for this long
STALE_PILL_MS = 600000  # Pills may advertise less often; tune once you see it

_IRQ_SCAN_RESULT = 5
_IRQ_SCAN_DONE = 6

# Tilt iBeacon UUID: A495BBxx-C5B1-4B44-B512-1370F02D74DE (xx = colour code)
_HEAD = b"\xa4\x95\xbb"
_TAIL = b"\xc5\xb1\x4b\x44\xb5\x12\x13\x70\xf0\x2d\x74\xde"

COLORS = {
    0x10: "Red", 0x20: "Green", 0x30: "Black", 0x40: "Purple",
    0x50: "Orange", 0x60: "Blue", 0x70: "Yellow", 0x80: "Pink",
}


def _tilt(d):
    """d = manufacturer data incl. company ID. Returns a reading tuple or None."""
    if not (d[4:7] == _HEAD and d[8:20] == _TAIL and d[7] in COLORS):
        return None
    major = (d[20] << 8) | d[21]
    minor = (d[22] << 8) | d[23]
    if major == 999:                 # battery-age beacon, not a reading
        return None
    if minor >= 5000:                # Tilt Pro: 0.1 F and 0.0001 SG
        return COLORS[d[7]], major, minor, 4, None
    return COLORS[d[7]], major * 10, minor * 10, 3, None


def _rapt(d, addr):
    """RAPT Pill: company ID 'RA' then 'PT' + version byte + 20 bytes, big endian."""
    body = d[4:25]                   # starts at the version byte
    if len(body) != 21:
        return None
    ver = body[0]
    try:
        if ver == 1:     # version, mac, temp, gravity, x, y, z, battery
            _v, _mac, traw, g, _x, _y, _z, bat = struct.unpack(">B6sHfhhhh", body)
        elif ver == 2:   # version, reserved, gv_valid, gv, temp, gravity, x, y, z, battery
            _v, _r, _ok, _gv, traw, g, _x, _y, _z, bat = struct.unpack(">BBBfHfhhhh", body)
        else:
            return None
    except Exception:
        return None
    sg = g / 1000
    if not (0.5 < sg < 2.0):         # also rejects NaN
        return None
    tc = traw / 128 - 273.15
    t10 = int((tc * 1.8 + 32) * 10 + 0.5)       # stored as 0.1 F like the Tilt
    label = "Pill %02X%02X" % (addr[4], addr[5])
    return label, t10, int(sg * 10000 + 0.5), 4, int(bat / 256 + 0.5)


def parse_adv(adv, addr):
    """Return (label, temp_x10_F, gravity_x10000, decimals, battery_pct|None) or None."""
    i, n = 0, len(adv)
    while i + 1 < n:
        length = adv[i]
        if length == 0:
            break
        if adv[i + 1] == 0xFF and length >= 26:
            d = bytes(adv[i + 2:i + 1 + length])
            if d[:4] == b"\x4c\x00\x02\x15":
                r = _tilt(d)
            elif d[:4] == b"RAPT":
                r = _rapt(d, addr)
            else:
                r = None
            if r:
                return r
        i += length + 1
    return None


def fmt_temp(t10, celsius=False, decimals=0):
    f = t10 / 10
    if celsius:
        f = (f - 32) * 5 / 9
    return (("%%.%df" % decimals) % f) + ("C" if celsius else "F")


def fmt_grav(g10000, places=3):
    return ("%%.%df" % places) % (g10000 / 10000)


class Scanner:
    def __init__(self):
        self.ble = bluetooth.BLE()
        # label -> [temp_x10_F, gravity_x10000, rssi, last_seen_ms, decimals, battery, stale_ms]
        self.devs = {}
        self.scans = 0
        self.state = "Off"
        self.last_scan = None
        self.last_beacon = None     # ticks_ms of the last Tilt/Pill reading
        self._restart = False

    def start(self):
        self.ble.active(True)
        self.ble.irq(self._irq)
        self._begin()

    def _begin(self):
        try:
            # active scan: also requests scan responses
            self.ble.gap_scan(SCAN_MS, 30000, 30000, True)
            self.state = "Scanning"
        except OSError:
            self.state = "Error"

    def _irq(self, event, data):
        if event == _IRQ_SCAN_RESULT:
            _addr_type, addr, _adv_type, rssi, adv = data
            r = parse_adv(adv, addr)
            if r:
                label, t10, g, places, bat = r
                now = time.ticks_ms()
                self.last_beacon = now
                stale = STALE_PILL_MS if label.startswith("Pill") else STALE_TILT_MS
                self.devs[label] = [t10, g, rssi, now, places, bat, stale]
        elif event == _IRQ_SCAN_DONE:
            self.scans += 1
            self.last_scan = time.ticks_ms()
            self._restart = True

    def poll(self):
        """Call regularly from the main loop."""
        if self._restart:
            self._restart = False
            now = time.ticks_ms()
            for k in [k for k, d in self.devs.items()
                      if time.ticks_diff(now, d[3]) > d[6]]:
                del self.devs[k]
            self._begin()

    def sorted_devices(self):
        """List of (label, record), Tilt colours and Pills in name order."""
        return sorted(self.devs.items())

    def seconds_since_scan(self):
        if self.last_scan is None:
            return None
        return time.ticks_diff(time.ticks_ms(), self.last_scan) // 1000

    def seconds_since_beacon(self):
        """Seconds since the last decoded reading, or None if none yet."""
        if self.last_beacon is None:
            return None
        return time.ticks_diff(time.ticks_ms(), self.last_beacon) // 1000

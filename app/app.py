import config
import sys
import time
import network
import machine

SSID = config.SSID
PASSWORD = config.PASSWORD

USE_WDT = False          # set False while developing
WDT_TIMEOUT_MS = 8000
RESTART_DELAY_S = 3
TEMP_C = True      # True = show Celsius, False = Fahrenheit

REDRAW_S = 0.1

wdt = None
oled = None
scanner = None

page = 0            # 0 = summary, 1 = wifi detail, 2 = ble detail
NUM_PAGES = 3
_last_press = 0
_button = None      # keep a reference so the IRQ isn't garbage collected


STATUS_TEXT = {
    network.STAT_IDLE: "Idle",
    network.STAT_CONNECTING: "Connecting",
    network.STAT_WRONG_PASSWORD: "Wrong password",
    network.STAT_NO_AP_FOUND: "AP not found",
    network.STAT_CONNECT_FAIL: "Connect failed",
    network.STAT_GOT_IP: "Connected",
}

def feed():
    if wdt:
        wdt.feed()

def init_oled():
    global oled
    try:
        import oled as oled_mod
        oled = oled_mod.OLED()
    except Exception as e:
        oled = None
        log_crash(e)             # display is optional; keep running without it

def init_ble():
    global scanner
    try:
        import ble_scan
        scanner = ble_scan.Scanner()
        scanner.start()
    except Exception as e:
        scanner = None
        log_crash(e)       # BLE is optional; keep running without it

def _on_key(pin):
    global page, _last_press
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_press) > 250:     # debounce
        _last_press = now
        page = (page + 1) % NUM_PAGES

def init_button():
    global _button
    _button = machine.Pin(17, machine.Pin.IN, machine.Pin.PULL_UP)   # KEY1
    _button.irq(trigger=machine.Pin.IRQ_FALLING, handler=_on_key)

def draw(*rows):
    if oled:
        try:
            oled.lines(*rows)
        except Exception:
            pass

def draw_wifi(wlan, start):
    status = wlan.status()
    text = STATUS_TEXT.get(status, "Status %d" % status)
    up = (time.ticks_ms() - start) // 1000
    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        try:
            rssi = "%d dBm" % wlan.status("rssi")
        except Exception:
            rssi = "n/a"
        draw("WiFi: " + text, SSID, "", "IP address:", ip, "", "RSSI: " + rssi,
             "Up: %ds" % up)
    else:
        draw("WiFi: " + text, SSID, "", "IP: --", "", "", "", "Up: %ds" % up)

def draw_summary(wlan, start):
    if wlan.isconnected():
        wifi = "WiFi: Connected"
        ip = wlan.ifconfig()[0]
    else:
        wifi = "WiFi: " + STATUS_TEXT.get(wlan.status(), "Down")
        ip = "IP: --"

    if scanner is None:
        draw(wifi, ip, "BLE: unavailable", "", "", "", "", "Up: " + fmt_uptime(start))
        return

    import ble_scan
    devs = scanner.sorted_devices()
    n = len(devs)
    lines = ["%s %s %s" % (label,
                           ble_scan.fmt_temp(d[0], TEMP_C),
                           ble_scan.fmt_grav(d[1], 3))
             for label, d in devs]
    if n > 3:
        lines = lines[:2] + ["+%d more" % (n - 2)]
    if n == 0:
        lines = ["(none yet)"]
    lines += [""] * (3 - len(lines))

    draw(wifi, ip, ble_status_line(), "Found: %d" % n,
         lines[0], lines[1], lines[2], "Up: " + fmt_uptime(start))

def draw_ble():
    if scanner is None:
        draw("BLE: unavailable")
        return
    import ble_scan
    devs = scanner.sorted_devices()
    n = len(devs)
    pages = max(1, (n + 1) // 2)               # 2 devices per screen
    p = (time.ticks_ms() // 4000) % pages      # rotate every 4 s
    head = "Found: %d" % n
    if pages > 1:
        head += " p%d/%d" % (p + 1, pages)
    rows = [ble_status_line(), head]
    now = time.ticks_ms()
    for label, d in devs[p * 2:p * 2 + 2]:
        rows.append("%s %ddBm" % (label, d[2]))
        detail = "%s %s" % (ble_scan.fmt_temp(d[0], TEMP_C, 1),
                            ble_scan.fmt_grav(d[1], d[4]))
        if d[5] is not None:
            detail += " %d%%" % d[5]           # Pill battery
        rows.append(detail)
        rows.append("Seen " + fmt_ago(time.ticks_diff(now, d[3]) // 1000))
    if n == 0:
        rows += ["Nothing found", "Searching..."]
    draw(*rows)

def fmt_uptime(start):
    s = time.ticks_diff(time.ticks_ms(), start) // 1000
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if d:
        return "%dd %dh %dm" % (d, h, m)
    return "%dh %02dm %02ds" % (h, m, s)

def fmt_ago(s):
    if s < 60:
        return "%ds ago" % s
    if s < 3600:
        return "%dm ago" % (s // 60)
    return "%dh ago" % (s // 3600)

def ble_status_line():
    if scanner.state != "Scanning":
        return "BLE: " + scanner.state          # e.g. "BLE: Error"
    ago = scanner.seconds_since_beacon()
    if ago is None:
        return "Beacon: none"                   # nothing received yet
    return "Beacon: " + fmt_ago(ago)            # e.g. "Beacon: 12s ago"

def draw_status(wlan, start):
    if page == 1:
        draw_wifi(wlan, start)
    elif page == 2:
        draw_ble()
    else:
        draw_summary(wlan, start)

def connect_wifi(start, timeout=20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(SSID, PASSWORD)
        t = time.time()
        while not wlan.isconnected() and time.time() - t < timeout:
            feed()
            draw_status(wlan, start)
            time.sleep(REDRAW_S)
    return wlan

def main():
    start = time.ticks_ms()
    init_oled()
    init_ble()
    init_button()
    led = machine.Pin("LED", machine.Pin.OUT)
    draw("Booting...")
    wlan = connect_wifi(start)
    last_blink = time.ticks_ms()
    while True:
        feed()
        if scanner:                 # <-- new
            scanner.poll()
        if not wlan.isconnected():
            wlan = connect_wifi(start)
        draw_status(wlan, start)

        blink_ms = 1000 if wlan.isconnected() else 100
        if time.ticks_diff(time.ticks_ms(), last_blink) >= blink_ms:
            led.toggle()
            last_blink = time.ticks_ms()

        time.sleep(REDRAW_S)

def log_crash(exc):
    try:
        with open("crash.log", "w") as f:
            sys.print_exception(exc, f)
    except Exception:
        pass

def run():
    global wdt
    if USE_WDT:
        wdt = machine.WDT(timeout=WDT_TIMEOUT_MS)
    try:
        main()
    except Exception as e:
        log_crash(e)
        draw("CRASHED", "", type(e).__name__, "", "Rebooting...")
        time.sleep(RESTART_DELAY_S)
        machine.reset()

run()

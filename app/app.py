import sys
import time
import network
import machine
import json

import config
from oled import OLED
from wifi import Wifi
from ble_scan import Scanner

from mqtt import Mqtt


WATCHDOG_TIMER = {
    'ENABLED': True,
    'TIMEOUT': 5_000
}

USE_WATCHDOG_TIMER = True
RESTART_DELAY_S = 1

BLINK_MS = 500

MAIN_LOOP_SLEEP_MS = 50

MQTT_TOPIC = "fermentation"
MQTT_INTERVAL_MS = 180_000 # 180s/3min, stale device is 5 minutes
MQTT_INTERVAL_HEALTHCHECK_MS = 60_000 # 60s


class Watchdog:
    def __init__(self):
        self.wdt = None

    def enable(self):
        self.wdt = machine.WDT(timeout=WATCHDOG_TIMER['TIMEOUT'])

    def feed(self):
        if self.wdt:
            self.wdt.feed()


class Application:
    def __init__(self, watchdog):
        self.start = self.last_blink = self.last_mqtt = self.last_mqtt_healthcheck = time.ticks_ms()
        self.led = machine.Pin("LED", machine.Pin.OUT)

        self.watchdog = watchdog

        self.oled = None
        self.init_oled()

        self.wifi = None
        self.init_wifi()

        self.scanner = None
        self.init_scanner()

        self.mqtt = None
        self.init_mqtt()

    def run(self):
        if self.wifi:
            self.wifi.connect()

        if self.scanner:
            self.scanner.start()

        while True:
            watchdog.feed()

            rows = []
            if self.wifi:
                if self.wifi.connected():
                    self.led.value(1)
                else:
                    self.blink_led()

                self.wifi.poll()

                status = self.wifi.status()
                rows.append(f"Wifi: {status[0]}")
                rows.extend(status[1:])
            else:
                rows.append("Failed to WIFI")

            if self.mqtt:
                self.mqtt.poll()
                if self.mqtt.connected:
                    rows.append(f"MQTT connected")
                    if time.ticks_diff(time.ticks_ms(), self.last_mqtt_healthcheck) > MQTT_INTERVAL_HEALTHCHECK_MS:
                        self.mqtt.publish(f"{MQTT_TOPIC}/status", b"online")
                        self.last_mqtt_healthcheck = time.ticks_ms()
                    if time.ticks_diff(time.ticks_ms(), self.last_mqtt) > MQTT_INTERVAL_MS:
                        for device in self.scanner.devices.values():
                            msg = {
                                "label": device.label,
                                "temperature": device.temperature,
                                "gravity": device.gravity,
                            }
                            if device.type == "pill":
                                msg["battery"] = device.battery

                            self.mqtt.publish(f"{MQTT_TOPIC}/{device.type}/{device.label}", json.dumps(msg))
                        self.last_mqtt = time.ticks_ms()

                else:
                    if self.mqtt.last_error:
                        rows.append(f"MQTT {self.mqtt.last_error}")
                    else:
                        rows.append(f"MQTT not connected")
            else:
                rows.append("Failed to MQTT")

            if self.scanner:
                self.scanner.poll()
                rows.append("")
                rows.append(f"{len(self.scanner.devices)} device found")
                sorted_devices = self.scanner.sorted_devices()[:2]
                for _label, device in sorted_devices:
                    rows.append(f"{device.label}: {round(device.temperature)}c {device.gravity} last seen {round(time.ticks_diff(time.ticks_ms(), device.timestamp) / 1000)}s")
            else:
                rows.append("Failed to init BLE")

            rows.append(f"Up {self.uptime()}")
            self.draw(*rows)

            time.sleep_ms(MAIN_LOOP_SLEEP_MS)

    def uptime(self):
        s = time.ticks_diff(time.ticks_ms(), self.start) // 1000
        d, s = divmod(s, 86400)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        if d:
            return "%dd %dh %dm" % (d, h, m)
        return "%dh %02dm %02ds" % (h, m, s)

    def blink_led(self):
        if time.ticks_diff(time.ticks_ms(), self.last_blink) >= BLINK_MS:
            self.led.toggle()
            self.last_blink = time.ticks_ms()

    def init_oled(self):
        try:
            self.oled = OLED()
        except Exception as e:
            log_crash(e)
            return

        self.oled.init_display()

    def init_wifi(self):
        try:
            self.wifi = Wifi()
        except Exception as e:
            log_crash(e)
            return

    def init_scanner(self):
        try:
            self.scanner = Scanner()
        except Exception as e:
            log_crash(e)
            return

    def init_mqtt(self):
        try:
            if self.wifi:
                self.mqtt = Mqtt(self.wifi, config.MQTT_SERVER, will=(f"{MQTT_TOPIC}/status".encode(), b"offline", True))
        except Exception as e:
            log_crash(e)
            return

    def draw(self, *rows):
        if self.oled:
            self.oled.lines(*rows)


watchdog = Watchdog()

def log_crash(e):
    try:
        with open("crash.log", "w") as f:
            sys.print_exception(e, f)
    except Exception:
        pass

    try:
        sys.print_exception(e)
    except Exception:
        pass

def run():
    if WATCHDOG_TIMER['ENABLED']:
        watchdog.enable()

    try:
        app = Application(watchdog)
        app.draw("Booting...")
        app.run()
    except Exception as e:
        log_crash(e)

        time.sleep(RESTART_DELAY_S)
        machine.reset()

run()

import sys
import time
import network
import machine

import config
from oled import OLED
from wifi import Wifi


WATCHDOG_TIMER = {
    'ENABLED': True,
    'TIMEOUT': 5_000
}

USE_WATCHDOG_TIMER = True
RESTART_DELAY_S = 1

BLINK_MS = 500

MAIN_LOOP_SLEEP_MS = 50


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
        self.start = self.last_blink = time.ticks_ms()
        self.led = machine.Pin("LED", machine.Pin.OUT)

        self.watchdog = watchdog

        self.oled = None
        self.init_oled()

        self.wifi = None
        self.init_wifi()

    def run(self):
        if self.wifi:
            self.wifi.connect()

        while True:
            watchdog.feed()

            if self.wifi:
                if self.wifi.connected():
                    self.led.value(1)
                else:
                    self.blink_led()

                self.wifi.poll()
                status = self.wifi.status()
                self.draw(f"Wifi: {status[0]}", *status[1:])

            time.sleep_ms(MAIN_LOOP_SLEEP_MS)

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

        self.oled._init_display()

    def init_wifi(self):
        try:
            self.wifi = Wifi()
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

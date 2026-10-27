import time
from binascii import hexlify
from umqtt.simple import MQTTClient


class Mqtt:
    NO_WIFI = "No WiFi"          # waiting for the wifi to come up
    WAITING = "Waiting"          # failed; waiting before the next attempt
    CONNECTED = "Connected"

    def __init__(self, wifi, server, client_id=None, port=0, user=None,
                 password=None, keepalive=30, connect_timeout_s=4,
                 retry_s=5, max_retry_s=60, will=None):
        """wifi: any object with a .connected property (your Wifi class).
        will: optional (topic, message, retain) last-will tuple."""
        if client_id is None:
            import machine
            client_id = b"pico-" + hexlify(machine.unique_id())
        self.wifi = wifi
        self.server = server
        self.client_id = client_id
        self.port = port
        self.user = user
        self.password = password
        self.keepalive = keepalive             # seconds; 0 disables pings
        self.io_timeout = connect_timeout_s    # socket timeout for connect and I/O
        self.retry_ms = retry_s * 1000
        self.max_retry_ms = max_retry_s * 1000
        self.will = will

        self.client = None
        self.status = Mqtt.NO_WIFI
        self.last_error = None
        self.attempts = 0                      # failed attempts since last success
        self.published = 0                     # successful publishes (total)
        self._backoff_ms = self.retry_ms
        self._wait_ms = 0
        self._t = 0
        self._last_tx = 0

    # --- public API ---------------------------------------------------

    @property
    def connected(self):
        return self.status == Mqtt.CONNECTED

    def poll(self):
        """Call often from the main loop. Blocks only while a connect
        attempt is in progress (at most about connect_timeout_s)."""
        now = time.ticks_ms()

        if not self.wifi.connected:
            if self.client:
                self._close()                  # wifi gone: drop the dead socket
            self.status = Mqtt.NO_WIFI
            return

        if self.status == Mqtt.NO_WIFI:        # wifi just came back
            self.status = Mqtt.WAITING
            self._wait_ms = 0                  # connect immediately
            self._t = now
            self._backoff_ms = self.retry_ms

        if self.status == Mqtt.WAITING:
            if time.ticks_diff(now, self._t) >= self._wait_ms:
                self._connect()
        elif self.keepalive and \
                time.ticks_diff(now, self._last_tx) >= self.keepalive * 500:
            self._ping()                       # ping at half the keepalive

    def publish(self, topic, msg, retain=False, qos=0):
        """Returns True if sent. On failure it returns False and a
        reconnect is scheduled for the next poll(). Nothing is queued."""
        if self.status != Mqtt.CONNECTED:
            return False
        try:
            self.client.publish(topic, msg, retain, qos)
        except Exception as e:
            self._fail("publish: " + type(e).__name__, immediate=True)
            return False
        self._last_tx = time.ticks_ms()        # any packet resets the keepalive timer
        self.published += 1
        return True

    # --- internals ----------------------------------------------------

    def _connect(self):
        c = MQTTClient(self.client_id, self.server, self.port,
                       self.user, self.password, self.keepalive)
        if self.will:
            topic, msg, retain = self.will
            c.set_last_will(topic, msg, retain)
        try:
            try:
                c.connect(timeout=self.io_timeout)
            except TypeError:                  # older umqtt.simple: no timeout argument
                c.connect()
            c.sock.settimeout(self.io_timeout)
        except Exception as e:
            self.client = c                    # so _fail() can close its socket
            self._fail("connect: " + type(e).__name__)
            return
        self.client = c
        self.status = Mqtt.CONNECTED
        self.last_error = None
        self.attempts = 0
        self._backoff_ms = self.retry_ms
        self._last_tx = time.ticks_ms()

    def _ping(self):
        try:
            c = self.client
            c.check_msg()                      # drains the previous PINGRESP
            c.sock.settimeout(self.io_timeout) # check_msg() switches the socket to blocking
            c.ping()
            self._last_tx = time.ticks_ms()
        except Exception as e:
            self._fail("ping: " + type(e).__name__, immediate=True)

    def _close(self):
        c, self.client = self.client, None
        if c:
            try:
                c.disconnect()
            except Exception:
                pass
            try:
                c.sock.close()
            except Exception:
                pass

    def _fail(self, reason, immediate=False):
        self.attempts += 1
        self.last_error = reason
        self._close()
        self.status = Mqtt.WAITING
        self._t = time.ticks_ms()
        if immediate:                          # was connected: retry on the next poll
            self._wait_ms = 0
        else:                                  # connect failed: back off 5, 10, 20... 60 s
            self._wait_ms = self._backoff_ms
            self._backoff_ms = min(self._backoff_ms * 2, self.max_retry_ms)

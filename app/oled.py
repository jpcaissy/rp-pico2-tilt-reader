import time
import framebuf
from machine import Pin, SPI

SCROLL_MS = 40
GAP = 4

class OLED(framebuf.FrameBuffer):
    def __init__(self):
        self.width = 128
        self.height = 64
        self.rst = Pin(12, Pin.OUT)
        self.cs = Pin(9, Pin.OUT)
        self.dc = Pin(8, Pin.OUT)
        self.cs(1)
        self.spi = SPI(1, baudrate=10_000_000, polarity=0, phase=0,
                       sck=Pin(10), mosi=Pin(11), miso=None)
        self.buffer = bytearray(self.width * self.height // 8)
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_HMSB)
        self._init_display()

    def _cmd(self, c):
        self.cs(1)
        self.dc(0)
        self.cs(0)
        self.spi.write(bytes([c]))
        self.cs(1)

    def _init_display(self):
        self.rst(1); time.sleep_ms(50)
        self.rst(0); time.sleep_ms(50)
        self.rst(1); time.sleep_ms(50)
        for c in (0xAE, 0x00, 0x10, 0xB0, 0xDC, 0x00, 0x81, 0x6F,
                  0x21, 0xA0, 0xC0, 0xA4, 0xA6, 0xA8, 0x3F, 0xD3,
                  0x60, 0xD5, 0x41, 0xD9, 0x22, 0xDB, 0x35, 0xAD,
                  0x8A, 0xAF):
            self._cmd(c)
        self.fill(0)
        self.show()

    def show(self):
        self._cmd(0xB0)
        for row in range(64):
            col = 63 - row
            self._cmd(0x00 + (col & 0x0F))
            self._cmd(0x10 + (col >> 4))
            self.cs(1)
            self.dc(1)
            self.cs(0)
            self.spi.write(self.buffer[row * 16:(row + 1) * 16])
            #strip = self.buffer[row * 16:(row + 1) * 16]
            #self.spi.write(bytes(REV[b] for b in reversed(strip)))
            self.cs(1)

    def lines(self, *rows):
        """Draw up to 8 rows; rows longer than 16 chars scroll left in a loop."""
        self.fill(0)
        step = time.ticks_ms() // SCROLL_MS
        for i, s in enumerate(rows[:8]):
            y = i * 8
            if len(s) <= 16:
                self.text(s, 0, y, 1)
            else:
                cycle = (len(s) + GAP) * 8   # pixels before the text repeats
                off = step % cycle
                self.text(s, -off, y, 1)          # current copy
                self.text(s, cycle - off, y, 1)   # wrap-around copy
        self.show()

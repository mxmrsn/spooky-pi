"""LED outputs: the real WS2812B chain over SPI, and a terminal preview."""

import sys
import time

import numpy as np

SPI_HZ = 6_400_000  # 8 SPI bits per WS2812 bit -> 156 ns per SPI bit
BIT0, BIT1 = 0b11000000, 0b11111000  # 312 ns high / 781 ns high
RESET_BYTES = 240  # >= 300 us low latches the frame


def encode(physical_rgb):
    """Physical uint8 RGB (n, 3) -> SPI bytes for WS2812B (GRB order, MSB first)."""
    grb = np.ascontiguousarray(physical_rgb[:, [1, 0, 2]], dtype=np.uint8).ravel()
    bits = np.unpackbits(grb)
    return b"\x00" + np.where(bits, BIT1, BIT0).astype(np.uint8).tobytes() + bytes(RESET_BYTES)


class SpiStrip:
    """WS2812B chain on SPI MOSI (GPIO10). Needs SPI enabled; on a Pi 4 also set
    core_freq_min=500 in /boot/firmware/config.txt so the SPI clock doesn't drift."""

    def __init__(self, bus=0, device=0):
        import spidev
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = SPI_HZ
        self.spi.mode = 0

    def write(self, physical_rgb):
        self.spi.writebytes2(encode(physical_rgb))

    def close(self):
        self.spi.close()


class TerminalStrip:
    """Draws the glasses in a truecolor terminal (works over SSH). Rate-limited."""

    ROWS, COLS = 9, 21  # canvas per eye

    def __init__(self, layout, fps=20, stream=sys.stdout):
        self.layout, self.stream = layout, stream
        self.interval = 1 / fps
        self._last = 0.0
        self._drawn = False
        self.status = ""
        inv = np.empty_like(layout.perm)
        inv[layout.perm] = np.arange(layout.n)
        self.inverse = inv  # logical i -> physical index
        px = layout.all
        centre_col = np.where(px.eye == 0, self.COLS // 2, self.COLS + 3 + self.COLS // 2)
        dx = px.x - np.where(px.eye == 0, -1.25, 1.25)  # offset from the eye centre, -1..1
        rows = np.round(self.ROWS // 2 - px.y * (self.ROWS // 2)).astype(int)
        cols = np.round(centre_col + dx * (self.COLS // 2 - 1)).astype(int)  # chars are ~2:1 tall
        self.cells = list(zip(rows, cols))

    def write(self, physical_rgb):
        now = time.monotonic()
        if now - self._last < self.interval:
            return
        self._last = now
        logical = physical_rgb[self.inverse].astype(float)
        # undo gamma/brightness roughly so dim colours are visible on a monitor
        cfg = self.layout.cfg
        screen = (np.clip(logical / 255 / max(cfg.brightness, 1e-3), 0, 1) ** (1 / cfg.gamma) * 255).astype(int)
        width = 2 * self.COLS + 3
        grid = [[" "] * width for _ in range(self.ROWS)]
        for (r, c), (red, g, b) in zip(self.cells, screen):
            grid[r][c] = f"\x1b[38;2;{red};{g};{b}m●\x1b[0m"
        lines = ["".join(row) for row in grid] + [f"\x1b[2K{self.status}"]
        out = (f"\x1b[{len(lines)}A" if self._drawn else "") + "\n".join(lines) + "\n"
        self.stream.write(out)
        self.stream.flush()
        self._drawn = True

    def close(self):
        pass


class NullStrip:
    def write(self, physical_rgb):
        pass

    def close(self):
        pass


class Leds:
    """Scene -> layout mapping -> strip, plus a status line for the terminal preview."""

    def __init__(self, layout, strip):
        self.layout, self.strip = layout, strip
        self.last = np.zeros((layout.n, 3), np.uint8)

    def show(self, frame):
        self.last = self.layout.to_physical(frame)
        self.strip.write(self.last)

    def set_status(self, text):
        if isinstance(self.strip, TerminalStrip):
            self.strip.status = text

    def close(self):
        try:
            self.strip.write(np.zeros((self.layout.n, 3), np.uint8))
        finally:
            self.strip.close()

"""The Teensy 4.1 on USB that drives the LED glasses and reads the PIRs.

Protocol (firmware: teensy/spooky_teensy):
  Pi -> Teensy  LED frame: A5 5A <n> <n x R,G,B> <sum of the RGB bytes & 0xFF>
                "?": ask for the hello line and the PIR levels
  Teensy -> Pi  "spooky-teensy <version> leds=<max> pirs=<k> frames=<good> bad=<bad>"  at boot and after "?"
                "S <levels>"  e.g. "S 01", PIR 1 first; on every change and every 0.5 s

The Teensy blanks the LEDs if no frame arrives for 2 s, so the link resends the
last frame while the show is quiet. The strip and the PIR inputs share one link
per port; it reopens the port on its own if the Teensy is unplugged or resets.
"""

import glob
import logging
import threading
import time

import numpy as np

log = logging.getLogger(__name__)

SYNC = b"\xa5\x5a"
BY_ID = "/dev/serial/by-id/*Teensyduino*"
KEEPALIVE = 0.5  # resend the last frame after this long without one
RETRY = 2.0  # seconds between reconnect attempts


def find_port():
    ports = sorted(glob.glob(BY_ID))
    if not ports:
        raise OSError(f"no Teensy on USB (nothing matches {BY_ID})")
    return ports[0]


def open_serial(port):
    import serial
    return serial.Serial(port or find_port(), timeout=0.1, write_timeout=1.0)


def encode_frame(physical_rgb):
    """Physical uint8 RGB (n, 3) -> one LED frame for the firmware."""
    data = np.ascontiguousarray(physical_rgb, dtype=np.uint8).tobytes()
    n = len(data) // 3
    if n > 255:
        raise ValueError(f"{n} LEDs is more than one frame can carry")
    return SYNC + bytes([n]) + data + bytes([sum(data) & 0xFF])


class TeensyLink:
    """One USB serial connection; use connect() so the strip and the PIRs share it."""

    def __init__(self, port="", opener=open_serial, clock=time.monotonic, start=True):
        self.port, self.opener, self.clock = port, opener, clock
        self.hello = None  # the firmware's hello line, once seen
        self.levels = []  # last reported PIR levels
        self.inputs = []
        self.users = 0
        self.lock = threading.RLock()  # guards the port and the frame
        self.ser = None
        self.frame = None
        self.last_write = -1e9
        self.next_retry = 0.0
        self.buf = b""
        self.warned = False
        self.stop = threading.Event()
        self._open()  # raises if there's no Teensy, so callers can fall back
        self.thread = None
        if start:
            self.thread = threading.Thread(target=self._run, daemon=True, name="teensy")
            self.thread.start()

    def _open(self):
        with self.lock:
            self.ser = self.opener(self.port)
            self.ser.write(b"?")
            if self.frame is not None:
                self._send(self.frame)

    def _drop(self, err):
        with self.lock:
            if self.ser is None:
                return
            log.warning("Teensy link lost (%s); reconnecting", err)
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
            self.next_retry = self.clock() + RETRY
        self._levels("0" * len(self.levels))  # unknown now: report quiet

    def _send(self, data):  # caller holds the lock
        if self.ser is None:
            return
        try:
            self.ser.write(data)
            self.last_write = self.clock()
        except OSError as e:
            self._drop(e)

    def send_leds(self, physical_rgb):
        frame = encode_frame(physical_rgb)
        with self.lock:
            self.frame = frame
            self._send(frame)

    def _levels(self, bits):
        self.levels = [int(c == "1") for c in bits]
        for inp in list(self.inputs):
            if inp.index < len(self.levels):
                inp._set(self.levels[inp.index])

    def feed(self, chunk):
        self.buf += chunk
        *lines, self.buf = self.buf.split(b"\n")
        if len(self.buf) > 1024:
            self.buf = b""
        for raw in lines:
            line = raw.decode("ascii", "replace").strip()
            if line.startswith("S "):
                self._levels(line[2:])
            elif line.startswith("spooky-teensy"):
                self.hello = line
                log.info("Teensy: %s", line)
            elif line and self.hello is None and not self.warned:
                self.warned = True
                log.warning("Teensy sent %r: is the spooky firmware flashed? (scripts/teensy-flash.sh)", line[:80])

    def step(self):
        """One pass of the background thread: read, keep the LEDs alive, reconnect."""
        ser = self.ser
        if ser is None:
            if self.clock() >= self.next_retry:
                try:
                    self._open()
                    log.info("Teensy reconnected")
                except OSError:
                    self.next_retry = self.clock() + RETRY
            return False
        try:
            chunk = ser.read(ser.in_waiting or 1)
        except Exception as e:  # pyserial raises odd types when the device vanishes
            self._drop(e)
            return False
        if chunk:
            self.feed(chunk)
        with self.lock:
            if self.frame is not None and self.clock() - self.last_write > KEEPALIVE:
                self._send(self.frame)
        return True

    def _run(self):
        while not self.stop.is_set():
            if not self.step():
                self.stop.wait(0.2)

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=1)
        with self.lock:
            if self.ser is not None:
                self.ser.close()
                self.ser = None


_links = {}
_links_lock = threading.Lock()


def connect(port=""):
    """The shared link for `port` ("" = the first Teensy found), opened on first use."""
    with _links_lock:
        link = _links.get(port)
        if link is None:
            link = _links[port] = TeensyLink(port)
        link.users += 1
        return link


def release(link):
    with _links_lock:
        link.users -= 1
        if link.users <= 0:
            _links.pop(link.port, None)
            link.close()


class TeensyStrip:
    """The WS2812B chain on the Teensy. Same interface as SpiStrip."""

    def __init__(self, port=""):
        self.link = connect(port)

    def write(self, physical_rgb):
        self.link.send_leds(physical_rgb)

    def close(self):
        release(self.link)


class TeensyInput:
    """One PIR as reported by the Teensy, shaped like gpiozero's DigitalInputDevice."""

    def __init__(self, index, port="", link=None):
        self.index = index
        self.link = link or connect(port)
        self.owned = link is None
        self.when_activated = self.when_deactivated = None
        levels = self.link.levels
        self.value = levels[index] if index < len(levels) else 0
        self.link.inputs.append(self)

    def _set(self, v):
        if v == self.value:
            return
        self.value = v
        callback = self.when_activated if v else self.when_deactivated
        if callback is not None:
            callback()

    def close(self):
        if self in self.link.inputs:
            self.link.inputs.remove(self)
            if self.owned:
                release(self.link)

"""The Teensy 4.1 on USB that drives the LED glasses (pin 1) and the handpiece strip (pin 8).

Protocol (firmware: teensy/spooky_teensy):
  Pi -> Teensy  LED frame: A5 <5A + channel> <n> <n x R,G,B> <sum of the RGB bytes & 0xFF>
                (channel 0 = glasses, 1 = handpiece)
                "?": ask for the hello line
  Teensy -> Pi  "spooky-teensy <version> leds=<max> hand=<max> frames=<good> bad=<bad>"  at boot and after "?"

The Teensy blanks a channel if no frame arrives for 2 s, so the link resends each
channel's last frame while the show is quiet. Everything using the Teensy shares one link per
port; it reopens the port on its own if the Teensy is unplugged or resets.
"""

import glob
import logging
import threading
import time

import numpy as np

log = logging.getLogger(__name__)

SYNC = b"\xa5\x5a"  # + channel on the second byte
GLASSES, HANDPIECE = 0, 1
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


def encode_frame(physical_rgb, channel=GLASSES):
    """Physical uint8 RGB (n, 3) -> one LED frame for the firmware."""
    data = np.ascontiguousarray(physical_rgb, dtype=np.uint8).tobytes()
    n = len(data) // 3
    if n > 255:
        raise ValueError(f"{n} LEDs is more than one frame can carry")
    return bytes([SYNC[0], SYNC[1] + channel, n]) + data + bytes([sum(data) & 0xFF])


class TeensyLink:
    """One USB serial connection; use connect() so every user shares it."""

    def __init__(self, port="", opener=open_serial, clock=time.monotonic, start=True):
        self.port, self.opener, self.clock = port, opener, clock
        self.hello = None  # the firmware's hello line, once seen
        self.users = 0
        self.lock = threading.RLock()  # guards the port and the frames
        self.ser = None
        self.frames = {}  # channel -> last frame sent
        self.last_write = {}  # channel -> when it was sent
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
            for channel, frame in self.frames.items():
                self._send(channel, frame)

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

    def _send(self, channel, data):  # caller holds the lock
        if self.ser is None:
            return
        try:
            self.ser.write(data)
            self.last_write[channel] = self.clock()
        except OSError as e:
            self._drop(e)

    def send_leds(self, physical_rgb, channel=GLASSES):
        frame = encode_frame(physical_rgb, channel)
        with self.lock:
            self.frames[channel] = frame
            self._send(channel, frame)

    def feed(self, chunk):
        self.buf += chunk
        *lines, self.buf = self.buf.split(b"\n")
        if len(self.buf) > 1024:
            self.buf = b""
        for raw in lines:
            line = raw.decode("ascii", "replace").strip()
            if line.startswith("S "):
                pass  # status lines from firmware before v3: ignored
            elif line.startswith("spooky-teensy"):
                self.hello = line
                log.info("Teensy: %s", line)
            elif line and self.hello is None and not self.warned:
                self.warned = True
                log.warning("Teensy sent %r: is the spooky firmware flashed? (scripts/pc/teensy-flash.sh)", line[:80])

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
            for channel, frame in self.frames.items():
                if self.clock() - self.last_write.get(channel, -1e9) > KEEPALIVE:
                    self._send(channel, frame)
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
    """One WS2812B chain on the Teensy (GLASSES or HANDPIECE). Same interface as TerminalStrip and NullStrip."""

    def __init__(self, port="", channel=GLASSES):
        self.link, self.channel = connect(port), channel

    def write(self, physical_rgb):
        self.link.send_leds(physical_rgb, self.channel)

    def close(self):
        release(self.link)


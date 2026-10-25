"""Motion inputs: the PIR sensors, and a keyboard stand-in for simulation."""

import queue
import sys
import threading
import time


class PirSensors:
    """PIR modules. poll() returns the indices of sensors that fired since last call.

    `devices` are shaped like gpiozero's DigitalInputDevice: Pi GPIO pins or the
    Teensy's inputs (see hw.open_pirs).
    """

    def __init__(self, devices):
        self._events = queue.SimpleQueue()
        self.sensors = list(devices)
        for i, s in enumerate(self.sensors):
            s.when_activated = lambda i=i: self._events.put(i)

    def poll(self):
        fired = []
        while not self._events.empty():
            fired.append(self._events.get())
        return fired

    def active(self):
        return any(s.value for s in self.sensors)

    def close(self):
        for s in self.sensors:
            s.close()


class PirMonitor:
    """Owns the PIR pins and records their levels for the Studio's live scope.

    `pins` label the sensors. `devices` are objects with `.value` and `when_activated` /
    `when_deactivated` (gpiozero DigitalInputDevice, or the Teensy's inputs); tests pass fakes. sample() is called from the
    Studio's LED loop (50 Hz); edges arrive on gpiozero's (or the Teensy link's) thread.
    """

    WINDOW = 15.0  # seconds of trace kept

    def __init__(self, pins, devices=None, clock=time.monotonic):
        if devices is None:
            from gpiozero import DigitalInputDevice
            devices = [DigitalInputDevice(p, pull_up=False) for p in pins]
        self.pins, self.devices, self.clock = list(pins), devices, clock
        self.lock = threading.Lock()
        self.trace = []  # (t, [levels])
        self.events = queue.SimpleQueue()
        self.stats = [{"pulses": 0, "rise": None, "last_high": None, "high_total": 0.0} for _ in pins]
        self.t0 = clock()
        for i, d in enumerate(devices):
            d.when_activated = lambda i=i: self._edge(i, True)
            d.when_deactivated = lambda i=i: self._edge(i, False)
            if d.value:
                self.stats[i]["rise"] = self.t0

    def _edge(self, i, high):
        now = self.clock()
        with self.lock:
            st = self.stats[i]
            if high:
                st["rise"], st["pulses"] = now, st["pulses"] + 1
                self.events.put(i)
            elif st["rise"] is not None:
                st["last_high"] = now - st["rise"]
                st["high_total"] += st["last_high"]
                st["rise"] = None

    def levels(self):
        return [int(bool(d.value)) for d in self.devices]

    def sample(self, now=None):
        now = self.clock() if now is None else now
        lv = self.levels()
        with self.lock:
            self.trace.append((now, lv))
            while self.trace and self.trace[0][0] < now - self.WINDOW:
                self.trace.pop(0)

    def snapshot(self):
        now = self.clock()
        with self.lock:
            stats = []
            for st in self.stats:
                high_now = (now - st["rise"]) if st["rise"] is not None else 0.0
                stats.append({"pulses": st["pulses"], "last_high": st["last_high"], "high_now": round(high_now, 2),
                              "high_pct": round(100 * (st["high_total"] + high_now) / max(now - self.t0, 1e-6), 1)})
            trace = [[round(t - now, 3), *lv] for t, lv in self.trace]
        return {"available": True, "pins": self.pins, "levels": self.levels(), "trace": trace,
                "window": self.WINDOW, "stats": stats}

    def reset_stats(self):
        with self.lock:
            self.t0 = self.clock()
            for st, d in zip(self.stats, self.devices):
                st.update(pulses=0, last_high=None, high_total=0.0, rise=self.t0 if d.value else None)

    def close(self):
        for d in self.devices:
            d.close()


class MonitorInputs:
    """Show inputs fed by a PirMonitor (real sensors), plus the Studio's pretend-motion button."""

    HOLD = 3.0

    def __init__(self, monitor):
        self.monitor = monitor
        self._manual = queue.SimpleQueue()
        self._last_manual = -1e9
        while not monitor.events.empty():  # ignore triggers from before the show started
            monitor.events.get()

    def trigger(self, sensor=0):
        self._last_manual = time.monotonic()
        self._manual.put(sensor)

    def poll(self):
        fired = []
        for q in (self.monitor.events, self._manual):
            while not q.empty():
                fired.append(q.get())
        return fired

    def active(self):
        return any(self.monitor.levels()) or time.monotonic() - self._last_manual < self.HOLD

    def close(self):
        pass  # the Studio keeps owning the pins


class SimInputs:
    """Keyboard stand-in, one command per line on stdin:

        1 / 2   PIR sensor 1 / 2 fires
        f       toggle a face in front of the simulated camera
        q       quit
    Tests call trigger() instead.
    """

    HOLD = 3.0  # a simulated PIR output stays high this long

    def __init__(self, on_face_toggle=None, read_stdin=True):
        self._events = queue.SimpleQueue()
        self._last = -1e9
        self.on_face_toggle = on_face_toggle
        self.quit = False
        if read_stdin:
            threading.Thread(target=self._read, daemon=True).start()

    def trigger(self, sensor=0):
        self._last = time.monotonic()
        self._events.put(sensor)

    def _read(self):
        for line in sys.stdin:
            cmd = line.strip().lower()
            if cmd in ("1", "2"):
                self.trigger(int(cmd) - 1)
            elif cmd == "f" and self.on_face_toggle:
                self.on_face_toggle()
            elif cmd == "q":
                self.quit = True

    def poll(self):
        fired = []
        while not self._events.empty():
            fired.append(self._events.get())
        return fired

    def active(self):
        return time.monotonic() - self._last < self.HOLD

    def close(self):
        pass

"""Motion inputs: the PIR sensors, and a keyboard stand-in for simulation."""

import queue
import sys
import threading
import time


class PirSensors:
    """PIR modules on GPIO. poll() returns the indices of sensors that fired since last call."""

    def __init__(self, pins):
        from gpiozero import MotionSensor
        self._events = queue.SimpleQueue()
        self.sensors = []
        for i, pin in enumerate(pins):
            s = MotionSensor(pin)
            s.when_motion = lambda i=i: self._events.put(i)
            self.sensors.append(s)

    def poll(self):
        fired = []
        while not self._events.empty():
            fired.append(self._events.get())
        return fired

    def active(self):
        return any(s.motion_detected for s in self.sensors)

    def close(self):
        for s in self.sensors:
            s.close()


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

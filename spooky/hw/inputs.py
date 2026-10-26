"""Pretend visitors: the keyboard (--sim) and the Studio's "someone walks up" button.

The show wakes on faces from the camera; these let you wake it without one.
"""

import queue
import sys
import threading
import time


class SimInputs:
    """Keyboard stand-in, one command per line on stdin:

        w       someone walks up (wakes the show)
        f       toggle a face in front of the simulated camera
        q       quit
    The Studio and tests call trigger() instead.
    """

    HOLD = 3.0  # a walk-up keeps the show awake this long

    def __init__(self, on_face_toggle=None, read_stdin=True):
        self._events = queue.SimpleQueue()
        self._last = -1e9
        self.on_face_toggle = on_face_toggle
        self.quit = False
        if read_stdin:
            threading.Thread(target=self._read, daemon=True).start()

    def trigger(self):
        self._last = time.monotonic()
        self._events.put(0)

    def _read(self):
        for line in sys.stdin:
            cmd = line.strip().lower()
            if cmd == "w":
                self.trigger()
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

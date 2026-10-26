import time

import numpy as np

from spooky.hw.camera import FaceWatcher


class SilentThenLive:
    """A camera that returns nothing until it has been reopened, like one opened too early at boot."""

    def __init__(self):
        self.reopened = 0

    def flush(self):
        pass

    def read(self):
        return np.zeros((40, 30, 3), np.uint8) if self.reopened else None

    def reopen(self):
        self.reopened += 1

    def close(self):
        pass


class NoFaces:
    def detect(self, frame):
        return np.zeros((0, 15), np.float32)


def test_watcher_reopens_a_camera_that_gives_no_frames():
    cam = SilentThenLive()
    w = FaceWatcher(cam, NoFaces())
    w.REOPEN_AFTER = 0.2
    w.enable()
    deadline = time.monotonic() + 3
    while w.latest() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    w.close()
    assert cam.reopened == 1 and w.latest() is not None

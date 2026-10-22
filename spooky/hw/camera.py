"""Camera, face detection, and a background watcher the show polls."""

import glob
import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from ..scare import MODEL

ROTATIONS = {
    "none": None,
    "cw": cv2.ROTATE_90_CLOCKWISE,
    "ccw": cv2.ROTATE_90_COUNTERCLOCKWISE,
    "180": cv2.ROTATE_180,
}


def quiet_opencv():
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)  # hide OpenCV 5 DNN target warnings


class Camera:
    """USB camera (MJPG) with the mounting rotation applied to every frame."""

    def __init__(self, index=0, size=(1920, 1080), rotate="none"):
        self.rotation = ROTATIONS[rotate]
        self.cap = cv2.VideoCapture(index, cv2.CAP_V4L2) if hasattr(cv2, "CAP_V4L2") else cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera {index}")

    def read(self):
        ok, frame = self.cap.read()
        if not ok:
            return None
        return cv2.rotate(frame, self.rotation) if self.rotation is not None else frame

    def flush(self, n=3):
        """Drop frames buffered while nobody was reading."""
        for _ in range(n):
            self.cap.grab()

    def close(self):
        self.cap.release()


class SimCamera:
    """Stand-in camera: a dark empty scene, or a still photo of a face when face_on is set."""

    def __init__(self, face_images=(), size=(1080, 1920), fps=15):
        self.size, self.interval = size, 1 / fps
        self.faces = [img for img in (cv2.imread(p) for p in face_images) if img is not None]
        self.face_on = False
        rng = np.random.default_rng(0)
        self.empty = rng.integers(10, 40, (size[1], size[0], 3), dtype=np.uint8)
        self._i = 0

    @classmethod
    def from_captures(cls, folder):
        """Use earlier captures (not the scary versions) as the simulated visitors."""
        files = sorted(glob.glob(str(folder / "2*[0-9].jpg")))  # timestamped originals, not *_scary
        return cls(files[-5:])

    def toggle_face(self):
        self.face_on = not self.face_on and bool(self.faces)
        self._i += 1

    def read(self):
        time.sleep(self.interval)
        if self.face_on:
            return self.faces[self._i % len(self.faces)].copy()
        return self.empty.copy()

    def flush(self, n=3):
        pass

    def close(self):
        pass


class FaceDetector:
    """YuNet on a downscaled copy; returns rows in full-resolution pixels (box, 5 landmarks, score)."""

    def __init__(self, scale=1 / 3, min_score=0.7):
        self.scale, self.min_score = scale, min_score
        self.det = None
        self._size = None

    def detect(self, frame):
        h, w = frame.shape[:2]
        size = (max(1, round(w * self.scale)), max(1, round(h * self.scale)))
        if self.det is None:
            self.det = cv2.FaceDetectorYN.create(str(MODEL), "", size, self.min_score, 0.3, 20)
        if size != self._size:
            self.det.setInputSize(size)
            self._size = size
        _, faces = self.det.detect(cv2.resize(frame, size, interpolation=cv2.INTER_AREA))
        if faces is None:
            return np.zeros((0, 15), np.float32)
        faces = faces.copy()
        faces[:, :14] /= self.scale
        return faces


@dataclass
class Sighting:
    t: float
    frame: np.ndarray
    faces: np.ndarray = field(default_factory=lambda: np.zeros((0, 15), np.float32))

    @property
    def has_face(self):
        return len(self.faces) > 0

    def biggest_face_center(self):
        """(x, y) of the largest face, each in -0.5..0.5 of the frame, y down."""
        f = self.faces[np.argmax(self.faces[:, 2] * self.faces[:, 3])]
        h, w = self.frame.shape[:2]
        return (f[0] + f[2] / 2) / w - 0.5, (f[1] + f[3] / 2) / h - 0.5


class FaceWatcher:
    """Reads the camera and runs face detection in a background thread while enabled."""

    def __init__(self, camera, detector, clock=time.monotonic):
        self.camera, self.detector, self.clock = camera, detector, clock
        self._lock = threading.Lock()
        self._latest = None
        self._last_face = None
        self._enabled = threading.Event()
        self._stop = False
        self.fps = 0.0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enable(self):
        if not self._enabled.is_set():
            with self._lock:
                self._latest = self._last_face = None
            self._enabled.set()

    def disable(self):
        self._enabled.clear()

    def latest(self):
        with self._lock:
            return self._latest

    def last_face(self):
        with self._lock:
            return self._last_face

    def _run(self):
        flushed = False
        n, t0 = 0, time.monotonic()
        while not self._stop:
            if not self._enabled.wait(0.1):
                flushed = False
                continue
            if not flushed:
                self.camera.flush()
                flushed = True
            frame = self.camera.read()
            if frame is None:
                time.sleep(0.05)
                continue
            s = Sighting(self.clock(), frame, self.detector.detect(frame))
            with self._lock:
                self._latest = s
                if s.has_face:
                    self._last_face = s
            n += 1
            if time.monotonic() - t0 > 2:
                self.fps, n, t0 = n / (time.monotonic() - t0), 0, time.monotonic()

    def close(self):
        self._stop = True
        self._enabled.set()
        self._thread.join(timeout=2)
        self.camera.close()

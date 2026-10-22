"""The glasses as animations see them, and the mapping onto the physical LED chain.

Animations work on *logical* pixels: left ring, right ring, then the two pupils.
Each pixel carries its geometry seen from the front:

    eye     0 = left, 1 = right
    angle   0..1 clockwise from 12 o'clock
    mangle  mirrored angle: clockwise on the left eye, anticlockwise on the right,
            so effects using it are symmetric about the nose
    x, y    position in eye-radius units (eyes centred at x = -1.25 and +1.25, y up)
    pupil   True for the pupil pixels

`Layout.to_physical` turns a logical float frame into the bytes the strip needs,
applying the brightness cap, gamma and the current budget on the way.
"""

from dataclasses import dataclass

import numpy as np

EYE_X = (-1.25, 1.25)
MA_PER_CHANNEL = 20.0  # WS2812B draws ~20 mA per colour channel at full PWM
MA_IDLE = 1.0  # quiescent draw per pixel


@dataclass
class Pixels:
    """Geometry of a group of logical pixels (all of them, or e.g. just the rings)."""
    index: np.ndarray
    eye: np.ndarray
    angle: np.ndarray
    mangle: np.ndarray
    x: np.ndarray
    y: np.ndarray
    pupil: np.ndarray

    @property
    def n(self):
        return len(self.index)

    def subset(self, mask):
        return Pixels(*(getattr(self, f)[mask] for f in
                        ("index", "eye", "angle", "mangle", "x", "y", "pupil")))


class Layout:
    def __init__(self, cfg):
        """cfg: config.LedConfig"""
        self.cfg = cfg
        counts = dict(cfg.chain)
        self.ring_size = counts["left_ring"]
        if counts.get("right_ring") != self.ring_size:
            raise ValueError("Both rings must have the same number of pixels")
        rs = self.ring_size
        self.n = 2 * rs + 2

        eye = np.r_[np.zeros(rs), np.ones(rs), 0, 1].astype(int)
        angle = np.r_[np.arange(rs) / rs, np.arange(rs) / rs, 0, 0]
        pupil = np.r_[np.zeros(2 * rs, bool), True, True]
        mangle = np.where(eye == 1, (1 - angle) % 1, angle)
        radius = np.where(pupil, 0.0, 1.0)
        x = np.take(EYE_X, eye) + radius * np.sin(2 * np.pi * angle)
        y = radius * np.cos(2 * np.pi * angle)
        self.all = Pixels(np.arange(self.n), eye, angle, mangle, x, y, pupil)
        self.rings = self.all.subset(~pupil)
        self.pupils = self.all.subset(pupil)

        self.perm = self._physical_order(cfg)

    def _physical_order(self, cfg):
        """perm[p] = logical index shown by physical pixel p."""
        rs = self.ring_size
        base = {"left_ring": 0, "right_ring": rs, "left_pupil": 2 * rs, "right_pupil": 2 * rs + 1}
        perm = []
        for name, count in cfg.chain:
            if name not in base:
                raise ValueError(f"Unknown LED segment {name!r}")
            if name.endswith("pupil"):
                perm.append(base[name])
                continue
            side = 0 if name.startswith("left") else 1
            off, cw = cfg.ring_offset[side], cfg.ring_clockwise[side]
            for k in range(count):
                j = (k - off) % rs if cw else (off - k) % rs
                perm.append(base[name] + j)
        if sorted(perm) != list(range(self.n)):
            raise ValueError("LED chain must list each ring and pupil exactly once")
        return np.array(perm)

    def to_physical(self, frame):
        """Logical float RGB frame (n, 3) in 0..1 -> physical uint8 RGB (n, 3)."""
        pwm = np.clip(frame, 0.0, 1.0) ** self.cfg.gamma * self.cfg.brightness
        ma = pwm.sum() * MA_PER_CHANNEL + self.n * MA_IDLE
        budget = self.cfg.max_current_a * 1000
        if ma > budget:
            pwm *= (budget - self.n * MA_IDLE) / (ma - self.n * MA_IDLE)
        return np.round(pwm * 255).astype(np.uint8)[self.perm]

    def estimate_current_a(self, physical):
        return (physical.astype(float).sum() / 255 * MA_PER_CHANNEL + self.n * MA_IDLE) / 1000

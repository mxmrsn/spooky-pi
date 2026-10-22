"""LED effects. Each one renders colours for a group of pixels at time t.

An effect is any object with `render(t, px) -> (px.n, 3)` floats in 0..1, where
`t` is seconds since the scene started and `px` is a layout.Pixels group. Effects
read the geometry they care about (angle, mangle, eye, x, y), so the same effect
works on the rings, the pupils or everything.

Colours are RGB tuples in 0..1; `rgb("#ff2000")` converts hex.
"""

import math

import numpy as np


def rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


PALETTE = {
    "off": (0.0, 0.0, 0.0),
    "white": (1.0, 1.0, 1.0),
    "blood": rgb("#ff0000"),
    "ember": rgb("#ff3000"),
    "amber": rgb("#ff8000"),
    "toxic": rgb("#30ff00"),
    "slime": rgb("#00ff40"),
    "ghost": rgb("#a0d0ff"),
    "violet": rgb("#8000ff"),
    "magenta": rgb("#ff00a0"),
}


def color(c):
    """Accept a palette name, a hex string or an RGB tuple."""
    if isinstance(c, str):
        return np.array(PALETTE[c] if c in PALETTE else rgb(c))
    return np.array(c, float)


def _paint(level, col, background=None):
    """level (n,) in 0..1 blended between background and col -> (n, 3)."""
    level = np.clip(level, 0.0, 1.0)[:, None]
    out = level * color(col)
    if background is not None:
        out += (1 - level) * color(background)
    return out


def _hash(*arrays):
    """Cheap deterministic per-element pseudo-random numbers in 0..1."""
    h = np.zeros(np.broadcast(*arrays).shape)
    for i, a in enumerate(arrays):
        h = h + np.asarray(a, float) * (12.9898 + 61.7 * i)
    return np.modf(np.abs(np.sin(h) * 43758.5453))[0]


class Off:
    def render(self, t, px):
        return np.zeros((px.n, 3))


class Solid:
    def __init__(self, col, level=1.0):
        self.col, self.level = col, level

    def render(self, t, px):
        return _paint(np.full(px.n, self.level), self.col)


class Breathe:
    """Slow sine pulse between low and high brightness."""

    def __init__(self, col, period=4.0, low=0.08, high=1.0, phase=0.0):
        self.col, self.period, self.low, self.high, self.phase = col, period, low, high, phase

    def render(self, t, px):
        s = 0.5 - 0.5 * math.cos(2 * math.pi * (t / self.period + self.phase))
        return _paint(np.full(px.n, self.low + (self.high - self.low) * s), self.col)


class Comet:
    """Bright head(s) chasing round the rings with a fading tail.

    mirror=True spins the two eyes in opposite directions (symmetric about the nose).
    """

    def __init__(self, col, speed=0.8, tail=0.4, heads=1, mirror=True, background=None):
        self.col, self.speed, self.tail, self.heads = col, speed, tail, heads
        self.mirror, self.background = mirror, background

    def render(self, t, px):
        a = px.mangle if self.mirror else px.angle
        level = np.zeros(px.n)
        for k in range(self.heads):
            head = (t * self.speed + k / self.heads) % 1
            behind = (head - a) % 1
            level = np.maximum(level, np.clip(1 - behind / self.tail, 0, 1) ** 2)
        return _paint(level, self.col, self.background)


class Fill:
    """Rings fill up from 12 o'clock over `duration` seconds, both eyes together (countdown)."""

    def __init__(self, col, duration=3.0, background="off"):
        self.col, self.duration, self.background = col, duration, background

    def render(self, t, px):
        frac = min(max(t / self.duration, 0.0), 1.0)
        n_ring = max(len(np.unique(np.round(px.angle, 6))), 1)
        level = np.clip((frac - px.mangle) * n_ring, 0, 1)  # soft leading edge one pixel wide
        return _paint(level, self.col, self.background)


class Strobe:
    def __init__(self, col, hz=8.0, duty=0.4, background="off"):
        self.col, self.hz, self.duty, self.background = col, hz, duty, background

    def render(self, t, px):
        on = (t * self.hz) % 1 < self.duty
        return _paint(np.full(px.n, 1.0 if on else 0.0), self.col, self.background)


class Flicker:
    """Fire/candle flicker: every pixel wobbles on its own smooth noise."""

    def __init__(self, col, amount=0.6, speed=1.0, background=None):
        self.col, self.amount, self.speed, self.background = col, amount, speed, background

    def render(self, t, px):
        seed = px.index * 7.31
        s = t * self.speed
        wobble = (np.sin(s * 7.0 + seed) + np.sin(s * 13.3 + seed * 1.7) + np.sin(s * 23.9 + seed * 2.3)) / 3
        return _paint(1 - self.amount * (0.5 + 0.5 * wobble), self.col, self.background)


class Sparkle:
    """Random pixels flash briefly over a base colour."""

    def __init__(self, col, base="off", rate=6.0, decay=0.15):
        self.col, self.base, self.rate, self.decay = col, base, rate, decay

    def render(self, t, px):
        slot = math.floor(t / self.decay)
        since = (t - slot * self.decay) / self.decay
        chance = self.rate * self.decay / max(px.n, 1)
        lit = _hash(px.index, slot) < chance
        return _paint(np.where(lit, 1 - since, 0.0), self.col, self.base)


class Lightning:
    """Mostly dark with sudden double flashes at random moments."""

    def __init__(self, col="ghost", every=3.0, background="off"):
        self.col, self.every, self.background = col, every, background

    def render(self, t, px):
        slot = math.floor(t / self.every)
        start = float(_hash(slot)) * (self.every - 0.5)
        dt = t - slot * self.every - start
        if 0 <= dt < 0.06 or 0.12 <= dt < 0.2:  # the two flashes
            level = 1.0
        elif 0.2 <= dt < 0.6:  # afterglow
            level = 0.3 * (0.6 - dt) / 0.4
        else:
            level = 0.0
        return _paint(np.full(px.n, level), self.col, self.background)


class Rainbow:
    def __init__(self, speed=0.3, saturation=1.0, mirror=True):
        self.speed, self.saturation, self.mirror = speed, saturation, mirror

    def render(self, t, px):
        a = px.mangle if self.mirror else px.angle
        h = (a + t * self.speed) % 1 * 6
        x = 1 - np.abs(h % 2 - 1)
        z = np.zeros(px.n)
        o = np.ones(px.n)
        sector = h.astype(int) % 6
        r = np.choose(sector, [o, x, z, z, x, o])
        g = np.choose(sector, [x, o, o, x, z, z])
        b = np.choose(sector, [z, z, x, o, o, x])
        out = np.stack([r, g, b], 1)
        return out * self.saturation + (1 - self.saturation)


class Gaze:
    """An iris spot on each ring that looks in a direction, like eyes following you.

    Set `look` to an (dx, dy) direction seen from the front (dx right, dy up, each -1..1);
    the spot glides there. Near (0, 0) the spot fades and the ring glows evenly: staring
    straight at you.
    """

    def __init__(self, col, background=None, width=0.1, glide=0.15):
        self.col, self.background, self.width, self.glide = col, background, width, glide
        self.look = (0.0, 0.0)
        self._cur = np.zeros(2)
        self._t = None

    def render(self, t, px):
        dt = 0.0 if self._t is None else max(t - self._t, 0.0)
        self._t = t
        k = 1 - math.exp(-dt / self.glide) if self.glide > 0 else 1.0
        self._cur += (np.array(self.look, float) - self._cur) * k
        dx, dy = self._cur
        strength = min(math.hypot(dx, dy), 1.0)
        target = math.atan2(dx, dy) / (2 * math.pi) % 1
        dist = np.abs((px.angle - target + 0.5) % 1 - 0.5)
        spot = np.exp(-(dist / self.width) ** 2) * strength + 0.25 * (1 - strength)
        return _paint(spot, self.col, self.background)


class Talk:
    """Scales another effect by a speech loudness envelope, so the LEDs 'mouth' the words.

    envelope: 0..1 samples at `rate` Hz (audio.ClipInfo.envelope). After it ends the
    effect sits at `floor`.
    """

    def __init__(self, effect, envelope, rate=50, floor=0.15):
        self.effect, self.envelope, self.rate, self.floor = effect, envelope, rate, floor

    def render(self, t, px):
        i = int(t * self.rate)
        level = float(self.envelope[i]) if 0 <= i < len(self.envelope) else 0.0
        return self.effect.render(t, px) * (self.floor + (1 - self.floor) * level)


class Blend:
    """Mix two effects: a + b, clipped (e.g. Breathe base plus Sparkle)."""

    def __init__(self, a, b):
        self.a, self.b = a, b

    def render(self, t, px):
        return np.clip(self.a.render(t, px) + self.b.render(t, px), 0, 1)


class Sequence:
    """Play effects one after another: Sequence((effect, seconds), ...); loops by default."""

    def __init__(self, *steps, loop=True):
        self.steps, self.loop = steps, loop
        self.total = sum(d for _, d in steps)

    def render(self, t, px):
        if self.loop:
            t %= self.total
        for effect, d in self.steps:
            if t < d:
                return effect.render(t, px)
            t -= d
        effect, d = self.steps[-1]
        return effect.render(d, px)

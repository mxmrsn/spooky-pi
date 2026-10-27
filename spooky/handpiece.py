"""The handpiece: a short WS2812B strip (8 LEDs) on Teensy pin 8, with its own looks.

A look is a name from LOOKS plus an optional colour: "strobe", or "strobe:#00ff00" in
config. Each show state has a look ([handpiece] looks); teammates can hold any look for
a while through the control API (POST /api/handpiece), which overrides the state's.
"""

import numpy as np

from .effects import Breathe, Comet, Fill, Flicker, Off, Solid, Strobe, color
from .layout import MA_IDLE, MA_PER_CHANNEL, Pixels

# name -> (factory(colour), default colour)
LOOKS = {
    "off": (lambda c: Off(), "off"),
    "glow": (lambda c: Solid(c, level=0.25), "blood"),
    "solid": (lambda c: Solid(c), "blood"),
    "pulse": (lambda c: Breathe(c, period=1.5, low=0.05, high=1.0), "blood"),
    "flicker": (lambda c: Flicker(c, amount=0.6, speed=1.5), "ember"),
    "strobe": (lambda c: Strobe(c, hz=4, duty=0.5), "blood"),  # kept slow, like the glasses' strobes
    "chase": (lambda c: Comet(c, speed=1.0, tail=0.5, mirror=False), "toxic"),
    "fill": (lambda c: Fill(c, duration=3.0), "white"),  # fills along the strip over 3 s (the countdown)
    "flash": (lambda c: Solid(c, level=0.35), "white"),
}


def parse(spec):
    """'strobe' or 'strobe:#ff0000' -> (look, colour or None). Raises ValueError if unknown."""
    look, _, col = spec.partition(":")
    if look not in LOOKS:
        raise ValueError(f"unknown handpiece look {look!r}; choose from {', '.join(LOOKS)}")
    if col:
        color(col)  # raises for a bad colour
    return look, col or None


def strip_pixels(n):
    """A straight strip, LED 0 first: angle runs 0..1 along it, so chases and fills go end to end."""
    along = np.arange(n) / max(n, 1)
    return Pixels(np.arange(n), np.zeros(n, int), along, along, np.linspace(-1, 1, n), np.zeros(n),
                  np.zeros(n, bool))


class Handpiece:
    def __init__(self, cfg, gamma, strip):
        self.cfg, self.gamma, self.strip = cfg, gamma, strip
        self.px = strip_pixels(cfg.leds)
        self.base = self.held = None  # (label, effect, start[, until])
        self.set_state("IDLE", 0.0)

    def _make(self, look, col):
        factory, default = LOOKS[look]
        return factory(col or default)

    def set_state(self, state, now):
        look, col = parse(self.cfg.looks.get(state, "off"))
        self.base = (look if not col else f"{look}:{col}", self._make(look, col), now)

    def hold(self, look, col, now, seconds=None):
        """Show this look instead of the state's, for `seconds` or until release()."""
        self.held = (look if not col else f"{look}:{col}", self._make(look, col), now,
                     now + seconds if seconds else None)

    def release(self):
        self.held = None

    def _active(self, now):
        if self.held is not None and (self.held[3] is None or now < self.held[3]):
            return self.held
        self.held = None
        return self.base

    def render(self, now):
        _, effect, start = self._active(now)[:3]
        pwm = np.clip(effect.render(now - start, self.px), 0, 1) ** self.gamma * self.cfg.brightness
        idle = len(pwm) * MA_IDLE
        ma = pwm.sum() * MA_PER_CHANNEL + idle
        budget = self.cfg.max_current_a * 1000
        if ma > budget:
            pwm *= (budget - idle) / (ma - idle)
        self.strip.write(np.round(pwm * 255).astype(np.uint8))

    def status(self, now):
        label = self._active(now)[0]
        held = self.held
        return {"look": label, "held": held is not None,
                "seconds_left": None if held is None or held[3] is None else round(held[3] - now, 1)}

    def close(self):
        try:
            self.strip.write(np.zeros((len(self.px.index), 3), np.uint8))
        finally:
            self.strip.close()

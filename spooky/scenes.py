"""Scenes: a rings effect plus a pupils effect, by name.

Add or tweak looks here. Each entry is a factory so every use starts fresh
(some effects, like Gaze, keep state). The show uses the names in STATE_SCENES;
`python -m spooky.demo` previews any of them.
"""

import numpy as np

from .effects import (Blend, Breathe, Comet, Fill, Flicker, Gaze, Lightning, Off, Rainbow, Sequence,
                      Solid, Sparkle, Strobe)


class Scene:
    def __init__(self, rings, pupils=None):
        self.rings = rings
        self.pupils = pupils if pupils is not None else rings

    def render(self, t, layout):
        frame = np.zeros((layout.n, 3))
        frame[layout.rings.index] = self.rings.render(t, layout.rings)
        frame[layout.pupils.index] = self.pupils.render(t, layout.pupils)
        return frame

    @property
    def gaze(self):
        """The Gaze effect in this scene, if any, so the show can steer it."""
        for e in (self.rings, self.pupils):
            if isinstance(e, Gaze):
                return e
        return None


SCENES = {
    # --- used by the show -------------------------------------------------------
    "idle": lambda: Scene(Breathe("blood", period=5, low=0.03, high=0.35),
                          Flicker("ember", amount=0.7, speed=0.5)),
    "awake": lambda: Scene(Comet("toxic", speed=1.2, tail=0.5, heads=2), Solid("blood")),
    "watching": lambda: Scene(Gaze("toxic", background=(0, 0.04, 0)), Solid("blood")),
    "countdown": lambda: Scene(Fill("white", duration=3.0, background=(0.05, 0, 0)), Strobe("blood", hz=2)),
    "flash": lambda: Scene(Solid("white")),
    "processing": lambda: Scene(Comet("violet", speed=2.0, tail=0.3, heads=3, mirror=False),
                                Breathe("magenta", period=0.8)),
    "reveal": lambda: Scene(Strobe("blood", hz=10), Solid("white")),
    "showing": lambda: Scene(Flicker("ember", amount=0.5, speed=1.5), Solid("blood")),
    "off": lambda: Scene(Off()),
    # --- extras to mix into the show or use as attract modes ------------------------
    "storm": lambda: Scene(Lightning("ghost", every=2.5), Breathe("ghost", period=2.5, low=0.0, high=0.3)),
    "toxic_sparkle": lambda: Scene(Blend(Breathe("slime", period=3, low=0.05, high=0.3),
                                         Sparkle("white", rate=4)), Solid("toxic")),
    "madness": lambda: Scene(Rainbow(speed=0.8), Strobe("white", hz=6)),
    "possessed": lambda: Scene(Sequence((Comet("blood", speed=3, heads=1), 1.5),
                                        (Strobe("blood", hz=12), 0.5),
                                        (Breathe("blood", period=1.0), 1.0)),
                               Flicker("amber", amount=0.9, speed=2)),
}

# Which scene each show state uses
STATE_SCENES = {
    "IDLE": "idle",
    "AWAKE": "awake",
    "WATCHING": "watching",
    "COUNTDOWN": "countdown",
    "CAPTURE": "flash",
    "PROCESSING": "processing",
    "REVEAL": "reveal",
    "SHOWING": "showing",
}


def make(name):
    try:
        return SCENES[name]()
    except KeyError:
        raise KeyError(f"Unknown scene {name!r}; choose from {', '.join(SCENES)}") from None

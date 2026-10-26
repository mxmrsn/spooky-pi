"""Scenes: a rings effect plus a pupils effect, by name. These are the eye states
the show (and teammates, through the control API in spooky/web) switch between.

The current glasses have no pupil LEDs, so only the rings effect shows; the pupils
effect is kept for builds that fit them.

Add or tweak looks here. Each entry is a factory so every use starts fresh
(some effects, like Gaze, keep state). The show uses the names in STATE_SCENES;
`python -m spooky.demo` previews any of them. Scenes made in the Studio come from
custom_scenes.json (see custom.py) and are added on top by load_custom().
"""

import logging

import numpy as np

from . import custom
from .audio import ENVELOPE_HZ
from .effects import (
    Blend,
    Breathe,
    Comet,
    Fill,
    Flicker,
    Gaze,
    Lightning,
    Off,
    Rainbow,
    Sequence,
    Solid,
    Sparkle,
    Strobe,
    Talk,
)


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
            e = e.effect if isinstance(e, Talk) else e
            if isinstance(e, Gaze):
                return e
        return None


# Flashes and strobes are kept gentle: dimmer and slower than the LEDs can go, since
# full-brightness strobing at arm's length was too much.
SOFT_WHITE = (0.35, 0.35, 0.35)
SOFT_BLOOD = (0.45, 0.0, 0.0)

SCENES = {
    # --- used by the show -------------------------------------------------------
    "idle": lambda: Scene(Breathe("blood", period=5, low=0.03, high=0.35),
                          Flicker("ember", amount=0.7, speed=0.5)),
    "awake": lambda: Scene(Comet("toxic", speed=1.2, tail=0.5, heads=2), Solid("blood")),
    "watching": lambda: Scene(Gaze("toxic", background=(0, 0.04, 0)), Solid("blood")),
    "countdown": lambda: Scene(Fill((0.6, 0.6, 0.6), duration=3.0, background=(0.05, 0, 0)), Strobe("blood", hz=2)),
    "flash": lambda: Scene(Solid(SOFT_WHITE)),
    "processing": lambda: Scene(Comet("violet", speed=2.0, tail=0.3, heads=3, mirror=False),
                                Breathe("magenta", period=0.8)),
    "reveal": lambda: Scene(Strobe(SOFT_BLOOD, hz=3, duty=0.5, background=(0.06, 0, 0)), Solid("white")),
    "showing": lambda: Scene(Flicker("ember", amount=0.5, speed=1.5), Solid("blood")),
    "off": lambda: Scene(Off()),
    # --- extras to mix into the show or use as attract modes ------------------------
    "storm": lambda: Scene(Lightning("ghost", every=2.5), Breathe("ghost", period=2.5, low=0.0, high=0.3)),
    "toxic_sparkle": lambda: Scene(Blend(Breathe("slime", period=3, low=0.05, high=0.3),
                                         Sparkle("white", rate=4)), Solid("toxic")),
    "madness": lambda: Scene(Rainbow(speed=0.8), Strobe(SOFT_WHITE, hz=4)),
    "possessed": lambda: Scene(Sequence((Comet("blood", speed=3, heads=1), 1.5),
                                        (Strobe(SOFT_BLOOD, hz=5), 0.5),
                                        (Breathe("blood", period=1.0), 1.0)),
                               Flicker("amber", amount=0.9, speed=2)),
    # --- character signatures (pick one in sounds/voices/<name>/voice.toml) --------
    "rage": lambda: Scene(Flicker("blood", amount=0.4, speed=3), Solid("white")),
    "glare": lambda: Scene(Breathe("amber", period=1.5, low=0.3, high=1.0), Solid("amber")),
    "venom": lambda: Scene(Comet("toxic", speed=0.6, tail=0.8, heads=2), Solid("slime")),
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


BUILTIN = set(SCENES)
BUILTIN_STATE_SCENES = dict(STATE_SCENES)
log = logging.getLogger(__name__)


def load_custom(path=None):
    """(Re)load artist scenes and state assignments from custom_scenes.json. Bad entries are skipped."""
    for name in [n for n in SCENES if n not in BUILTIN]:
        del SCENES[name]
    STATE_SCENES.clear()
    STATE_SCENES.update(BUILTIN_STATE_SCENES)
    data = custom.load(path)
    for name, spec in data["scenes"].items():
        if name in BUILTIN:
            log.warning("custom scene %r ignored: that name is built in", name)
            continue
        try:
            custom.build(spec)  # validate now rather than mid-show
        except Exception as e:
            log.warning("custom scene %r skipped: %s", name, e)
            continue
        SCENES[name] = lambda spec=spec: Scene(*custom.build(spec))
    for state, name in data["state_scenes"].items():
        if state in STATE_SCENES and name in SCENES:
            STATE_SCENES[state] = name
    return data


def make(name):
    try:
        return SCENES[name]()
    except KeyError:
        raise KeyError(f"Unknown scene {name!r}; choose from {', '.join(SCENES)}") from None


def talking(line, fallback, pupils=True):
    """Scene while a voice line plays: the voice's own scene (or `fallback`), pulsing with the words.
    Without pupil LEDs (`pupils` False) a voice that talks with its pupils talks with the rings."""
    scene = make(line.voice.scene or fallback)
    env = line.info.envelope
    talk = "rings" if line.voice.talk == "pupils" and not pupils else line.voice.talk
    if talk in ("rings", "all"):
        scene.rings = Talk(scene.rings, env, ENVELOPE_HZ)
    if talk in ("pupils", "all"):
        scene.pupils = Talk(scene.pupils, env, ENVELOPE_HZ)
    return scene


load_custom()

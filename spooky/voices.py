"""Character voices: recorded lines (e.g. the bosses' catchphrases) with their own LED look.

    sounds/voices/<name>/voice.toml        optional settings, see below
    sounds/voices/<name>/<event>/*.wav     lines for that show event

voice.toml:
    scene  = "rage"     # LED scene while this voice talks (default: keep the state's scene)
    talk   = "pupils"   # LEDs that pulse with the voice: pupils | rings | all | none
    weight = 1.0        # how often this voice is picked relative to the others

Events: see EVENTS. How likely a line is per event is audio.voice_chance in the config.
"""

import logging
import random
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import audio

log = logging.getLogger(__name__)

EVENTS = ("ambient", "awaken", "spotted", "hold_still", "countdown", "shutter", "scream", "outro")
AUDIO_EXTS = audio.SOUND_EXTS
TALK_TARGETS = ("pupils", "rings", "all", "none")


@dataclass
class Voice:
    name: str
    folder: Path
    scene: str | None = None
    talk: str = "pupils"
    weight: float = 1.0
    lines: dict = field(default_factory=dict)  # event -> [Path]


@dataclass
class Line:
    voice: Voice
    event: str
    info: audio.ClipInfo

    @property
    def path(self):
        return self.info.path

    @property
    def duration(self):
        return self.info.duration


def load_voice(folder):
    folder = Path(folder)
    v = Voice(folder.name, folder)
    cfg_file = folder / "voice.toml"
    if cfg_file.is_file():
        with open(cfg_file, "rb") as f:
            data = tomllib.load(f)
        unknown = set(data) - {"scene", "talk", "weight"}
        if unknown:
            raise ValueError(f"{cfg_file}: unknown setting(s) {', '.join(sorted(unknown))}")
        v.scene = data.get("scene", v.scene)
        v.talk = data.get("talk", v.talk)
        v.weight = float(data.get("weight", v.weight))
        if v.talk not in TALK_TARGETS:
            raise ValueError(f"{cfg_file}: talk must be one of {', '.join(TALK_TARGETS)}")
    for event in EVENTS:
        files = sorted(p for p in (folder / event).glob("*") if p.suffix.lower() in AUDIO_EXTS)
        if files:
            v.lines[event] = files
    return v


class VoiceBank:
    def __init__(self, folder, player, chance=None, rng=None):
        self.player = player
        self.chance = chance or {}
        self.rng = rng or random.Random()
        self.voices = []
        folder = Path(folder)
        if folder.is_dir():
            for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
                try:
                    self.voices.append(load_voice(sub))
                except Exception as e:
                    log.warning("voice %s skipped: %s", sub.name, e)
        self.busy_until = -1e9
        self.only = None  # restrict to one voice name (audition)
        self._last = None

    def has(self, event):
        return any(event in v.lines for v in self.voices)

    def pick(self, event, voice=None):
        """Choose a line for event (from one voice, or weighted across all). None if there are none."""
        voice = voice or self.only
        pool = [v for v in self.voices if event in v.lines and (voice is None or v.name == voice)]
        pool = [v for v in pool if v.weight > 0] or pool
        if not pool:
            return None
        v = self.rng.choices(pool, weights=[max(x.weight, 1e-6) for x in pool])[0]
        files = [p for p in v.lines[event] if p != self._last] or v.lines[event]  # avoid repeats
        path = self.rng.choice(files)
        try:
            info = audio.analyse(path)
        except Exception as e:
            log.warning("cannot read %s: %s", path, e)
            return None
        self._last = path
        return Line(v, event, info)

    def speak(self, event, now, force=False):
        """Maybe play a line for event. Never talks over itself. Returns the Line or None."""
        if now < self.busy_until:
            return None
        if not force and self.rng.random() >= self.chance.get(event, 0.0):
            return None
        line = self.pick(event)
        if line is None:
            return None
        try:
            self.player.play(line.path)
        except Exception as e:
            log.warning("could not play %s: %s", line.path.name, e)
            return None
        self.busy_until = now + line.duration
        log.info("%s says %s (%.1f s)", line.voice.name, line.path.name, line.duration)
        return line

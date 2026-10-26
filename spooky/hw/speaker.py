"""Sound playback: the speaker (pygame), a logging stand-in, and the sound-effect bank."""

import logging
import random
from pathlib import Path

from ..audio import SOUND_EXTS

log = logging.getLogger(__name__)



class PygamePlayer:
    """Plays through PipeWire/ALSA with pygame.mixer; overlapping sounds are fine."""

    def __init__(self, volume=1.0):
        import pygame
        pygame.mixer.init(frequency=44100)
        pygame.mixer.set_num_channels(8)
        self.pygame, self.volume, self.cache = pygame, volume, {}

    def play(self, path):
        snd = self.cache.get(path)
        if snd is None:
            snd = self.cache[path] = self.pygame.mixer.Sound(str(path))
            snd.set_volume(self.volume)
        snd.play()

    def stop(self):
        self.pygame.mixer.stop()

    def close(self):
        self.pygame.mixer.quit()


class LogPlayer:
    def play(self, path):
        log.info("sound: %s", Path(path).name)

    def stop(self):
        pass

    def close(self):
        pass


class SoundBank:
    """Picks a random file from sounds/<event>/ and plays it.

    Events used by the show: ambient, awaken, countdown, shutter, scream.
    A missing or empty folder just means silence for that event.
    """

    def __init__(self, folder, player):
        self.player = player
        self.sounds = {}
        folder = Path(folder)
        if folder.is_dir():
            for sub in folder.iterdir():
                files = sorted(p for p in sub.glob("*") if p.suffix.lower() in SOUND_EXTS) if sub.is_dir() else []
                if files:
                    self.sounds[sub.name] = files
        self._last = {}

    def play(self, event):
        files = self.sounds.get(event)
        if not files:
            log.debug("no sounds for %r", event)
            return None
        choices = [f for f in files if f != self._last.get(event)] or files  # avoid repeats
        path = random.choice(choices)
        self._last[event] = path
        try:
            self.player.play(path)
        except Exception as e:  # a bad file shouldn't stop the show
            log.warning("could not play %s: %s", path.name, e)
        return path

    def stop(self):
        self.player.stop()

    def close(self):
        self.player.close()

"""The show: a state machine driving LEDs, sounds, aiming LED, camera and display.

    IDLE ──PIR──> AWAKE ──face──> WATCHING ──face held (lock-on)──> COUNTDOWN ──> CAPTURE
      ^             │ timeout        │ face lost / timeout     │ face lost
      │             v                v                         v
      ├──────── IDLE <────────── AWAKE <──────────────────── AWAKE
      │
      └── SHOWING <── REVEAL <── PROCESSING <── CAPTURE

step(now) does all the work, so tests drive it with a fake clock.
"""

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path

import cv2

from . import scenes
from .effects import Fill, color
from .scare import scare

log = logging.getLogger(__name__)

PROCESS_TIMEOUT = 20.0
FACE_FRESH = 0.5  # the countdown only starts if the face was seen this recently
LOCK_FROM, LOCK_TO = color("toxic"), color("blood")  # eye spot colour over the lock-on
HOLD_TEXT = "HOLD STILL!"


class State(Enum):
    IDLE = "idle"
    AWAKE = "awake"
    WATCHING = "watching"
    COUNTDOWN = "countdown"
    CAPTURE = "capture"
    PROCESSING = "processing"
    REVEAL = "reveal"
    SHOWING = "showing"


# Per state: (sound event on entry, aiming LED mode, camera on)
STATE_SETUP = {
    State.IDLE: (None, "off", False),
    State.AWAKE: ("awaken", "pulse", True),
    State.WATCHING: ("spotted", "on", True),
    State.COUNTDOWN: ("countdown", "blink", True),
    State.CAPTURE: ("shutter", "off", True),
    State.PROCESSING: (None, "off", False),
    State.REVEAL: ("scream", "blink", False),
    State.SHOWING: ("outro", "off", False),
}
# States whose own LED scene must not be replaced by a talking voice's scene
KEEP_SCENE = {State.COUNTDOWN, State.CAPTURE}


class Show:
    def __init__(self, cfg, dev, clock=time.monotonic, scare_fn=scare, executor=None):
        self.cfg, self.sc, self.dev = cfg, cfg.show, dev
        self.clock, self.scare_fn = clock, scare_fn
        self.executor = executor or ThreadPoolExecutor(max_workers=1)
        self.state = None
        self.scene = None
        self.entered = 0.0
        self.rearm_until = 0.0
        self.last_activity = -1e9
        self.face_since = None
        self.face_seen = -1e9
        self.job = None
        self.scary = None
        self.overlay = None  # (scene, start, end) while a voice line plays
        self.force_voice = False  # audition: always speak when a voice has a line
        self.told_hold = False  # "hold still!" already given during this lock-on
        self.hold_card = False  # display is showing the HOLD STILL card
        now = clock()
        self.next_ambient = now + random.uniform(*self.sc.ambient_interval)
        self.dev.display.idle()
        self._enter(State.IDLE, now)

    # ------------------------------------------------------------------ plumbing
    def _enter(self, state, now, quiet=False):
        log.info("%s -> %s", self.state.name if self.state else "start", state.name)
        self.state, self.entered = state, now
        self.scene = scenes.make(scenes.STATE_SCENES[state.name])
        if isinstance(self.scene.rings, Fill):
            self.scene.rings.duration = self.sc.countdown
        if state in KEEP_SCENE:
            self.overlay = None
        if state is State.WATCHING:
            self.told_hold = False
        if state in (State.IDLE, State.AWAKE) and self.hold_card:
            self.dev.display.idle()  # visitor left mid lock-on
            self.hold_card = False
        sound, aim, camera = STATE_SETUP[state]
        if sound and not quiet:
            self.cue(sound, now)
        self.dev.aim.set(aim)
        if self.dev.watcher is not None:
            (self.dev.watcher.enable if camera else self.dev.watcher.disable)()

    def cue(self, event, now):
        """Sound effect for event, plus maybe a character line with its talking LED scene."""
        self.dev.sounds.play(event)
        voices = getattr(self.dev, "voices", None)
        line = voices.speak(event, now, force=self.force_voice) if voices else None
        if line is not None and self.state not in KEEP_SCENE:
            scene = scenes.talking(line, scenes.STATE_SCENES[self.state.name])
            self.overlay = (scene, now, now + line.duration + 0.3)
        return line

    def active_scene(self, now):
        """(scene, its t) to render now: a talking voice's scene, else the state's."""
        if self.overlay is not None:
            scene, start, end = self.overlay
            if now < end:
                return scene, now - start
            self.overlay = None
        return self.scene, self.elapsed(now)

    def elapsed(self, now):
        return now - self.entered

    def _update_face(self, now):
        """Track how long a face has been continuously present; returns the latest sighting."""
        s = self.dev.watcher.latest() if self.dev.watcher else None
        if s is not None and s.has_face and now - s.t < self.sc.face_lost_grace:
            self.face_seen = s.t
            self.last_activity = now
            if self.face_since is None:
                self.face_since = now
        elif now - self.face_seen > self.sc.face_lost_grace:
            self.face_since = None
        return s

    def _steer_gaze(self, sighting):
        if sighting is None or not sighting.has_face:
            return
        hx, hy = sighting.biggest_face_center()
        dx = -2 * hx if self.cfg.camera.gaze_mirror else 2 * hx
        for scene in (self.scene, self.overlay[0] if self.overlay else None):
            if scene is not None and scene.gaze is not None:
                scene.gaze.look = (dx, -2 * hy)

    # ------------------------------------------------------------------ states
    def step(self, now):
        fired = self.dev.inputs.poll()
        if fired or self.dev.inputs.active():
            self.last_activity = now
        handler = getattr(self, f"_{self.state.value}")
        handler(now, fired)
        self.render(now)

    def render(self, now):
        scene, t = self.active_scene(now)
        self.dev.leds.show(scene.render(t, self.dev.layout))
        fps = f" cam {self.dev.watcher.fps:.0f} fps" if self.dev.watcher else ""
        self.dev.leds.set_status(f"{self.state.name:<10} {self.elapsed(now):5.1f} s{fps}   "
                                 "(1/2 = PIR, f = face, q = quit)")

    def _idle(self, now, fired):
        if fired and now >= self.rearm_until:
            self.face_since = None
            self._enter(State.AWAKE, now)
        elif now >= self.next_ambient:
            self.cue("ambient", now)
            self.next_ambient = now + random.uniform(*self.sc.ambient_interval)

    def _awake(self, now, fired):
        if self.dev.watcher is None:  # no camera: give them a scare anyway
            if self.elapsed(now) > 2.0:
                self.scary = None
                self._enter(State.REVEAL, now)
            return
        self._update_face(now)
        if self.face_since is not None:
            self._enter(State.WATCHING, now)
        elif now - self.last_activity > self.sc.awake_timeout:
            self._enter(State.IDLE, now)

    def _watching(self, now, fired):
        s = self._update_face(now)
        self._steer_gaze(s)
        if self.face_since is None:
            self._enter(State.AWAKE, now, quiet=True)
            return
        held = now - self.face_since
        fresh = now - self.face_seen < FACE_FRESH
        self._lock_on(min(held / self.sc.face_hold, 1.0))
        if not self.told_hold and fresh and held >= self.sc.hold_still_after:
            self.told_hold = True
            self.cue("hold_still", now)
            self.dev.display.card(HOLD_TEXT)
            self.hold_card = True
        if fresh and held >= self.sc.face_hold:
            self._enter(State.COUNTDOWN, now)

    def _lock_on(self, progress):
        """Eye spot narrows and turns from green to red as the lock-on completes."""
        for scene in (self.scene, self.overlay[0] if self.overlay else None):
            gaze = scene.gaze if scene is not None else None
            if gaze is not None:
                gaze.col = tuple(LOCK_FROM + (LOCK_TO - LOCK_FROM) * progress)
                gaze.width = 0.14 - 0.08 * progress

    def _countdown(self, now, fired):
        self._update_face(now)
        if self.face_since is None:
            self._enter(State.AWAKE, now, quiet=True)
        elif self.elapsed(now) >= self.sc.countdown:
            self._enter(State.CAPTURE, now)

    def _capture(self, now, fired):
        if self.elapsed(now) < self.sc.flash:
            return
        s = self.dev.watcher.last_face()
        if s is None:
            log.info("no face frame to capture")
            self._enter(State.AWAKE, now, quiet=True)
            return
        self.job = self.executor.submit(self._process, s.frame)
        self._enter(State.PROCESSING, now)

    def _processing(self, now, fired):
        if self.job.done():
            try:
                self.scary = self.job.result()
            except Exception:
                log.exception("scary processing failed")
                self._enter(State.IDLE, now)
                return
            self.dev.display.show(self.scary)
            self._enter(State.REVEAL, now)
        elif self.elapsed(now) > PROCESS_TIMEOUT:
            log.error("scary processing timed out")
            self._enter(State.IDLE, now)

    def _reveal(self, now, fired):
        if self.elapsed(now) >= self.sc.reveal:
            self._enter(State.SHOWING, now)

    def _showing(self, now, fired):
        if self.elapsed(now) >= self.sc.display_seconds:
            self.dev.display.idle()
            self.rearm_until = now + self.sc.rearm
            self._enter(State.IDLE, now)

    # ------------------------------------------------------------------ work
    def _process(self, frame):
        t0 = time.perf_counter()
        scary, n = self.scare_fn(frame, self.sc.grin, self.sc.eyes)
        log.info("scared %d face(s) in %.2f s", n, time.perf_counter() - t0)
        if self.sc.save_photos:
            self._save(frame, scary)
        return scary

    def _save(self, frame, scary):
        folder = self.cfg.path(self.cfg.captures)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        cv2.imwrite(str(folder / f"{stamp}.jpg"), frame)
        cv2.imwrite(str(folder / f"{stamp}_scary.jpg"), scary)
        photos = sorted(p for p in folder.glob("2*.jpg"))
        for old in photos[:max(0, len(photos) - 2 * self.sc.keep_photos)]:
            Path(old).unlink(missing_ok=True)

    # ------------------------------------------------------------------ loop
    def run(self):
        period = 1 / self.cfg.leds.fps
        nxt = self.clock()
        try:
            while True:
                self.step(self.clock())
                if not self.dev.display.pump() or getattr(self.dev.inputs, "quit", False):
                    break
                nxt += period
                delay = nxt - self.clock()
                if delay > 0:
                    time.sleep(delay)
                else:
                    nxt = self.clock()  # running behind; don't try to catch up
        finally:
            self.executor.shutdown(wait=False, cancel_futures=True)

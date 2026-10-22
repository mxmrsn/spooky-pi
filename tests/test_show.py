from concurrent.futures import Future

import numpy as np
import pytest

from spooky.config import Config
from spooky.hw import Devices
from spooky.hw.camera import Sighting
from spooky.hw.leds import Leds, NullStrip
from spooky.layout import Layout
from spooky.show import Show, State

DT = 0.05


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class Inputs:
    def __init__(self):
        self.pending = []
        self.motion = False

    def poll(self):
        fired, self.pending = self.pending, []
        return fired

    def active(self):
        return self.motion

    def close(self):
        pass


class Watcher:
    def __init__(self, clock):
        self.clock, self.enabled, self.face, self.fps = clock, False, False, 10.0
        self._last_face = None

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    def latest(self):
        if not self.enabled:
            return None
        frame = np.zeros((40, 30, 3), np.uint8)
        faces = np.array([[18, 10, 10, 10] + [0] * 10 + [0.9]], np.float32) if self.face else np.zeros((0, 15))
        s = Sighting(self.clock(), frame, faces)
        if self.face:
            self._last_face = s
        return s

    def last_face(self):
        return self._last_face

    def close(self):
        pass


class Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *a: self.calls.append((name, *a))


class Immediate:
    def submit(self, fn, *args):
        f = Future()
        try:
            f.set_result(fn(*args))
        except Exception as e:
            f.set_exception(e)
        return f

    def shutdown(self, **kw):
        pass


@pytest.fixture
def rig():
    cfg = Config()
    cfg.show.save_photos = False
    cfg.show.ambient_interval = [1e6, 1e6]
    clock = Clock()
    layout = Layout(cfg.leds)
    sounds, aim, display = Recorder(), Recorder(), Recorder()
    dev = Devices(layout, Leds(layout, NullStrip()), Inputs(), aim, sounds, display, Watcher(clock))
    show = Show(cfg, dev, clock=clock, scare_fn=lambda f, g, e: (f + 1, 1), executor=Immediate())
    return show, dev, clock, cfg.show


def run(show, clock, seconds):
    end = clock.t + seconds
    while clock.t < end:
        clock.t += DT
        show.step(clock.t)


def sounds_played(dev):
    return [c[1] for c in dev.sounds.calls if c[0] == "play"]


def test_full_scare_cycle(rig):
    show, dev, clock, sc = rig
    assert show.state is State.IDLE

    dev.inputs.pending.append(0)
    run(show, clock, DT)
    assert show.state is State.AWAKE and dev.watcher.enabled

    dev.watcher.face = True
    run(show, clock, 0.2)
    assert show.state is State.WATCHING

    run(show, clock, sc.face_hold)
    assert show.state is State.COUNTDOWN

    run(show, clock, sc.countdown)
    assert show.state is State.CAPTURE

    run(show, clock, sc.flash + 2 * DT)
    assert show.state is State.REVEAL
    shown = [c for c in dev.display.calls if c[0] == "show"]
    assert len(shown) == 1 and shown[0][1].max() == 1  # the scare_fn output reached the display
    assert not dev.watcher.enabled  # camera off while processing/revealing

    run(show, clock, sc.reveal)
    assert show.state is State.SHOWING
    run(show, clock, sc.display_seconds)
    assert show.state is State.IDLE
    assert dev.display.calls[-1] == ("idle",)
    assert sounds_played(dev) == ["awaken", "countdown", "shutter", "scream"]

    # re-arm delay: motion right away is ignored
    dev.inputs.pending.append(1)
    run(show, clock, DT)
    assert show.state is State.IDLE
    run(show, clock, sc.rearm)
    dev.inputs.pending.append(1)
    run(show, clock, DT)
    assert show.state is State.AWAKE


def test_face_lost_returns_to_awake_quietly(rig):
    show, dev, clock, sc = rig
    dev.inputs.pending.append(0)
    dev.watcher.face = True
    run(show, clock, 0.3)
    assert show.state is State.WATCHING
    dev.watcher.face = False
    run(show, clock, sc.face_lost_grace + 0.2)
    assert show.state is State.AWAKE
    assert sounds_played(dev) == ["awaken"]


def test_countdown_aborts_when_face_leaves(rig):
    show, dev, clock, sc = rig
    dev.inputs.pending.append(0)
    dev.watcher.face = True
    run(show, clock, sc.face_hold + 0.3)
    assert show.state is State.COUNTDOWN
    dev.watcher.face = False
    run(show, clock, sc.face_lost_grace + 0.2)
    assert show.state is State.AWAKE


def test_awake_times_out_without_face_or_motion(rig):
    show, dev, clock, sc = rig
    dev.inputs.pending.append(0)
    run(show, clock, DT)
    run(show, clock, sc.awake_timeout - 1)
    assert show.state is State.AWAKE
    run(show, clock, 1.5)
    assert show.state is State.IDLE


def test_motion_keeps_it_awake(rig):
    show, dev, clock, sc = rig
    dev.inputs.pending.append(0)
    dev.inputs.motion = True
    run(show, clock, sc.awake_timeout + 5)
    assert show.state is State.AWAKE


def test_processing_failure_goes_idle(rig):
    show, dev, clock, sc = rig

    def boom(*a):
        raise RuntimeError("bad photo")

    show.scare_fn = boom
    dev.inputs.pending.append(0)
    dev.watcher.face = True
    run(show, clock, sc.face_hold + sc.countdown + sc.flash + 0.5)
    assert show.state is State.IDLE


def test_no_camera_still_scares(rig):
    show, dev, clock, sc = rig
    dev.watcher = None
    dev.inputs.pending.append(0)
    run(show, clock, 2.2)
    assert show.state is State.REVEAL
    assert "scream" in sounds_played(dev)


def test_gaze_follows_face(rig):
    show, dev, clock, sc = rig
    dev.inputs.pending.append(0)
    dev.watcher.face = True  # face box at x 18..28 of a 30-wide frame: right side of the image
    run(show, clock, 0.3)
    assert show.state is State.WATCHING
    dx, dy = show.scene.gaze.look
    assert dx < 0  # image-right is the glasses' left seen from the front (gaze_mirror)

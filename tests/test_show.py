from concurrent.futures import Future

import numpy as np
import pytest

from spooky.config import Config
from spooky.hw import Devices
from spooky.hw.camera import Sighting
from spooky.hw.leds import Leds, NullStrip
from spooky.layout import Layout
from spooky.show import CLOSER_TEXT, DEVELOP_TEXT, HOLD_TEXT, IDLE_TEXT, Show, State

DT = 0.05


class Inputs:
    def __init__(self):
        self.pending = []
        self.present = False  # someone walked up and is still there

    def poll(self):
        fired, self.pending = self.pending, []
        return fired

    def active(self):
        return self.present

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
def rig(clock):
    cfg = Config()
    cfg.show.save_photos = False
    cfg.show.ambient_interval = [1e6, 1e6]
    layout = Layout(cfg.leds)
    sounds, display = Recorder(), Recorder()
    dev = Devices(layout, Leds(layout, NullStrip()), Inputs(), sounds, display, Watcher(clock))
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

    assert dev.display.calls[-1] == ("feed", HOLD_TEXT, "3")  # countdown over the camera feed
    run(show, clock, sc.countdown)
    assert show.state is State.CAPTURE
    assert dev.display.calls[-1] == ("flash",)

    run(show, clock, sc.flash + 2 * DT)
    assert show.state is State.REVEAL
    names = [c[0] for c in dev.display.calls]
    assert names[-2:] == ["still", "compare"] and dev.display.calls[-2][2] == DEVELOP_TEXT
    before, after = dev.display.calls[-1][1:]
    assert before.max() == 0 and after.max() == 1  # photo next to the scare_fn output
    assert not dev.watcher.enabled  # camera off while processing/revealing

    run(show, clock, sc.reveal)
    assert show.state is State.SHOWING
    run(show, clock, sc.display_seconds)
    assert show.state is State.IDLE
    assert dev.display.calls[-1] == ("feed", IDLE_TEXT)  # back to the camera feed
    assert sounds_played(dev) == ["awaken", "spotted", "hold_still", "countdown", "shutter", "scream", "outro"]

    # re-arm delay: a walk-up right away is ignored
    dev.inputs.pending.append(1)
    run(show, clock, DT)
    assert show.state is State.IDLE
    run(show, clock, sc.rearm)
    dev.inputs.pending.append(1)
    run(show, clock, DT)
    assert show.state is State.AWAKE


def test_face_wakes_it_without_a_walk_up(rig):
    show, dev, clock, sc = rig
    assert show.state is State.IDLE and dev.watcher.enabled  # camera watches while idle
    dev.watcher.face = True
    run(show, clock, sc.wake_face_hold / 2)
    assert show.state is State.IDLE  # a glimpse isn't enough
    run(show, clock, sc.wake_face_hold)
    assert show.state is State.AWAKE
    run(show, clock, show.entered + sc.awaken_time - 0.1 - clock.t)
    assert show.state is State.AWAKE  # eyes finish waking before "spotted"
    run(show, clock, 0.3)
    assert show.state is State.WATCHING and show.face_since == show.entered  # lock-on starts from scratch
    assert sounds_played(dev) == ["awaken", "spotted"]


def test_face_that_stays_starts_the_next_visit_after_rearm(rig):
    show, dev, clock, sc = rig
    dev.watcher.face = True
    run(show, clock, sc.wake_face_hold + sc.awaken_time + sc.face_hold + sc.countdown + 1)
    run(show, clock, sc.reveal + sc.display_seconds)
    assert show.state is State.IDLE
    run(show, clock, sc.rearm - 0.5)
    assert show.state is State.IDLE  # still re-arming
    run(show, clock, 0.5 + sc.wake_face_hold + 0.1)
    assert show.state is State.AWAKE


def test_visitor_who_stays_must_leave_first_if_configured(rig):
    show, dev, clock, sc = rig
    sc.leave_between_visits = True
    dev.watcher.face = True
    run(show, clock, sc.wake_face_hold + sc.awaken_time + sc.face_hold + sc.countdown + 1)
    assert show.state in (State.REVEAL, State.SHOWING)
    run(show, clock, sc.reveal + sc.display_seconds)
    assert show.state is State.IDLE
    run(show, clock, sc.rearm + 5)
    assert show.state is State.IDLE  # same face still there: no second photo
    dev.watcher.face = False
    run(show, clock, sc.face_lost_grace + 0.5)
    dev.watcher.face = True
    run(show, clock, sc.wake_face_hold + 0.2)
    assert show.state is State.AWAKE  # they left and came back


def test_face_wake_can_be_turned_off(rig):
    show, dev, clock, sc = rig
    sc.wake_on_face = False
    show._enter(State.IDLE, clock.t)
    assert not dev.watcher.enabled
    dev.watcher.face = True
    run(show, clock, 2)
    assert show.state is State.IDLE


def test_face_lost_returns_to_awake_quietly(rig):
    show, dev, clock, sc = rig
    dev.inputs.pending.append(0)
    dev.watcher.face = True
    run(show, clock, 0.3)
    assert show.state is State.WATCHING
    dev.watcher.face = False
    run(show, clock, sc.face_lost_grace + 0.2)
    assert show.state is State.AWAKE
    assert sounds_played(dev) == ["awaken", "spotted"]  # no second "awaken"


def test_countdown_aborts_when_face_leaves(rig):
    show, dev, clock, sc = rig
    dev.inputs.pending.append(0)
    dev.watcher.face = True
    run(show, clock, sc.face_hold + 0.3)
    assert show.state is State.COUNTDOWN
    dev.watcher.face = False
    run(show, clock, sc.face_lost_grace + 0.2)
    assert show.state is State.AWAKE


def test_awake_times_out_without_a_face(rig):
    show, dev, clock, sc = rig
    dev.inputs.pending.append(0)
    run(show, clock, DT)
    run(show, clock, sc.awake_timeout - 1)
    assert show.state is State.AWAKE
    run(show, clock, 1.5)
    assert show.state is State.IDLE


def test_someone_present_keeps_it_awake(rig):
    show, dev, clock, sc = rig
    dev.inputs.pending.append(0)
    dev.inputs.present = True
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


def test_voice_line_takes_over_leds_except_in_countdown(rig, tmp_path):
    from spooky import audio
    from spooky.voices import VoiceBank

    show, dev, clock, sc = rig
    for event in ("awaken", "countdown"):
        audio.write_wav(tmp_path / "boss" / event / "line.wav", np.full(8000 * 2, 0.3), 8000)
    (tmp_path / "boss" / "voice.toml").write_text('scene = "rage"\n')
    dev.voices = VoiceBank(tmp_path, Recorder(), chance={"awaken": 1.0, "countdown": 1.0})

    dev.inputs.pending.append(0)
    run(show, clock, DT)
    assert show.state is State.AWAKE and show.overlay is not None
    scene, t = show.active_scene(clock.t)
    assert scene is show.overlay[0] and scene is not show.scene
    run(show, clock, 2.5)
    assert show.overlay is None  # line finished: back to the state's scene

    dev.watcher.face = True
    run(show, clock, sc.face_hold + 0.3)
    assert show.state is State.COUNTDOWN
    assert show.overlay is None  # the countdown fill is never hidden


def test_lock_on_says_hold_still_and_prompts_if_they_leave(rig):
    show, dev, clock, sc = rig
    dev.inputs.pending.append(0)
    dev.watcher.face = True
    run(show, clock, 0.3)
    assert show.state is State.WATCHING
    green = show.scene.gaze.col
    run(show, clock, sc.hold_still_after)
    assert "hold_still" in sounds_played(dev)
    assert dev.display.calls[-1] == ("feed", HOLD_TEXT)
    assert show.scene.gaze.col[0] > green[0]  # spot is turning red
    assert show.state is State.WATCHING  # still locking on
    dev.watcher.face = False
    run(show, clock, sc.face_lost_grace + 0.2)
    assert show.state is State.AWAKE
    assert dev.display.calls[-1] == ("feed", CLOSER_TEXT)
    assert sounds_played(dev).count("hold_still") == 1


def test_step_closer_when_face_is_small(rig):
    show, dev, clock, sc = rig
    dev.inputs.pending.append(0)
    dev.watcher.face = True
    run(show, clock, 0.3)
    assert show.state is State.WATCHING
    sc.close_enough = 0.5  # the test face is a third of the frame wide
    run(show, clock, DT)
    assert dev.display.calls[-1] == ("feed", CLOSER_TEXT)


def test_eyes_override_holds_then_expires(rig):
    show, dev, clock, sc = rig
    show.command("eyes", "rage", 2.0)
    run(show, clock, DT)
    assert show.active_scene(clock.t)[0] is show.eyes_override[1]
    status = show.eyes_status()
    assert status["eyes"] == "rage" and status["override"]["seconds_left"] == pytest.approx(2.0 - DT, abs=0.06)
    assert status["show_state"] == "IDLE" and "glare" in status["eye_states"]
    run(show, clock, 2.0)
    assert show.eyes_override is None and show.eyes_status()["eyes"] == "idle"


def test_eyes_override_until_cleared_survives_state_changes(rig):
    show, dev, clock, sc = rig
    show.command("eyes", "storm", None)
    dev.inputs.pending.append(0)
    dev.watcher.face = True
    run(show, clock, 1.0)
    assert show.state is State.WATCHING and show.eyes_status()["eyes"] == "storm"
    show.command("eyes", None, None)
    run(show, clock, DT)
    assert show.eyes_override is None and show.eyes_status()["eyes"] == "watching"


def test_wake_and_reset_commands(rig):
    show, dev, clock, sc = rig
    show.command("reset")  # already idle: nothing to do
    show.command("wake")
    run(show, clock, DT)
    assert show.state is State.AWAKE
    show.command("wake")  # only wakes from IDLE
    run(show, clock, DT)
    assert show.state is State.AWAKE
    show.command("reset")
    run(show, clock, DT)
    assert show.state is State.IDLE and sounds_played(dev) == ["awaken"]


def test_control_api_over_http(rig):
    import json
    import urllib.error
    import urllib.request

    from spooky.web import WebServer

    show, dev, clock, sc = rig
    ctl = WebServer(0, show=show, host="127.0.0.1")
    base = f"http://127.0.0.1:{ctl.port}"

    def post(path, body):
        req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    try:
        assert b"POST /api/eyes" in urllib.request.urlopen(base + "/api").read()
        assert post("/api/eyes", {"state": "venom", "seconds": 3}) == (200, {"ok": True})
        run(show, clock, DT)
        status = json.load(urllib.request.urlopen(base + "/api/eyes"))
        assert status["eyes"] == "venom" and status["override"]["state"] == "venom"
        code, err = post("/api/eyes", {"state": "nope"})
        assert code == 400 and "unknown eye state" in err["error"]
        assert post("/api/eyes", {"state": "venom", "seconds": -1})[0] == 400
        assert post("/api/show", {"action": "dance"})[0] == 400
        assert post("/api/show", {"action": "wake"})[0] == 200
        run(show, clock, DT)
        assert show.state is State.AWAKE
        code, err = post("/api/imx", {"animation": "reveal"})
        assert code == 400 and "off" in err["error"]  # the rig has no i.MX
        assert post("/api/imx", {"animation": ""})[0] == 400
        code, err = post("/api/handpiece", {"look": "strobe"})
        assert code == 400 and "no handpiece" in err["error"]  # the rig has none
        assert "unknown handpiece look" in post("/api/handpiece", {"look": "disco"})[1]["error"]
        assert post("/api/handpiece", {"look": "pulse", "color": "#zz0000"})[0] == 400
    finally:
        ctl.close()


def test_imx_gets_an_animation_trigger_per_state(rig):
    import json
    import socket

    from spooky.hw.imx import ImxLink

    show, dev, clock, sc = rig
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(1)
    dev.imx = ImxLink("127.0.0.1", rx.getsockname()[1])
    show.cfg.imx.animations["WATCHING"] = ""  # nothing for this state
    dev.inputs.pending.append(0)
    dev.watcher.face = True
    run(show, clock, sc.awaken_time + 0.5)
    assert show.state is State.WATCHING
    show.command("imx", "thunder")
    run(show, clock, DT)
    got = [json.loads(rx.recv(4096)) for _ in range(2)]
    assert got == [{"cmd": "play", "animation": "awake", "state": "AWAKE", "seq": 1},
                   {"cmd": "play", "animation": "thunder", "state": None, "seq": 2}]
    dev.imx.close()
    rx.close()


def test_imx_trigger_without_a_receiver_doesnt_stop_the_show(rig):
    from spooky.hw.imx import ImxLink

    show, dev, clock, sc = rig
    dev.imx = ImxLink("127.0.0.1", 9)  # nothing listening
    dev.inputs.pending.append(0)
    run(show, clock, 0.5)
    assert show.state is State.AWAKE


def test_handpiece_follows_the_show_and_can_be_held(rig):
    from spooky.config import HandpieceConfig
    from spooky.handpiece import Handpiece
    from spooky.hw.leds import NullStrip

    show, dev, clock, sc = rig
    dev.handpiece = Handpiece(HandpieceConfig(), 2.2, NullStrip())
    dev.inputs.pending.append(0)
    run(show, clock, DT)
    assert show.eyes_status()["handpiece"]["look"] == "pulse"  # AWAKE's look
    show.command("handpiece", "strobe", "#00ff00", 1.0)
    run(show, clock, DT)
    hp = show.eyes_status()["handpiece"]
    assert hp["look"] == "strobe:#00ff00" and hp["held"]
    run(show, clock, 1.0)
    assert show.eyes_status()["handpiece"]["look"] == "pulse"
    show.command("handpiece", "glow", None, None)
    show.command("handpiece", None, None, None)  # released straight away
    run(show, clock, DT)
    assert not show.eyes_status()["handpiece"]["held"]

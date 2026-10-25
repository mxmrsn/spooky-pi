"""Studio logic, independent of the web server: LED preview, scene saving, sound library, show control.

All public methods are thread-safe (the web server calls them from many threads while
the LED loop runs in its own).
"""

import logging
import shutil
import threading
import time
import tomllib
from collections import deque
from pathlib import Path

import numpy as np

from .. import audio, custom, scenes
from ..hw import Devices
from ..hw.camera import Camera, FaceDetector, FaceWatcher, SimCamera
from ..hw.display import FileDisplay, StreamDisplay
from ..hw.inputs import MonitorInputs, SimInputs
from ..hw.leds import Leds
from ..hw.outputs import AimLed, SimAim, SoundBank
from ..show import Show
from ..voices import EVENTS, TALK_TARGETS, Line, VoiceBank, load_voice

log = logging.getLogger(__name__)

UPLOAD_EXTS = {".wav", ".ogg", ".mp3", ".m4a", ".aac", ".flac", ".opus", ".webm", ".mp4", ".mov", ".3gp", ".amr"}
MAX_UPLOAD = 100 * 1024 * 1024
EVENT_STATE = {"ambient": "IDLE", "awaken": "AWAKE", "spotted": "WATCHING", "hold_still": "WATCHING",
               "countdown": "COUNTDOWN", "shutter": "CAPTURE", "scream": "REVEAL", "outro": "SHOWING"}


class StudioError(Exception):
    """A problem to show the artist (bad name, missing file...)."""


class RecordingLeds(Leds):
    """Leds that also remember the last logical frame, for the on-screen glasses."""

    def __init__(self, layout, strip):
        super().__init__(layout, strip)
        self.logical = np.zeros((layout.n, 3))

    def show(self, frame):
        self.logical = np.clip(frame, 0, 1)
        super().show(frame)


class Studio:
    def __init__(self, cfg, leds, player, clock=time.monotonic, custom_path=None, pir=None):
        self.cfg, self.leds, self.player, self.clock = cfg, leds, player, clock
        self.layout = leds.layout
        self.sounds_root = cfg.path(cfg.audio.folder)
        self.raw_dir = cfg.path("raw")  # originals of uploads are kept here
        self.custom_path = custom_path
        self.lock = threading.RLock()
        self.events = deque(maxlen=30)
        self.scene_name = "idle"
        self.scene = scenes.make("idle")
        self.t0 = clock()
        self.overlay = None  # (scene, start, end) while a clip plays in preview
        self.show = None
        self.show_dev = None
        self._stop = threading.Event()
        self.pir = pir  # PirMonitor owning the real motion sensors, or None
        scenes.load_custom(custom_path)

    def note(self, text):
        log.info(text)
        self.events.appendleft({"t": time.strftime("%H:%M:%S"), "text": text})

    # ------------------------------------------------------------------ LED loop
    def tick(self):
        if self.pir is not None:
            self.pir.sample()
        with self.lock:
            now = self.clock()
            if self.show is not None:
                try:
                    self.show.step(now)
                except Exception:
                    log.exception("show step failed")
                    self.stop_show()
                return
            if self.overlay is not None and now >= self.overlay[2]:
                self.overlay = None
            scene, start = (self.overlay[0], self.overlay[1]) if self.overlay else (self.scene, self.t0)
            self.leds.show(scene.render(now - start, self.layout))

    def run(self):
        period = 1 / self.cfg.leds.fps
        while not self._stop.is_set():
            t = time.monotonic()
            self.tick()
            self._stop.wait(max(0.0, period - (time.monotonic() - t)))

    def stop(self):
        self._stop.set()
        self.stop_show()

    def frame(self):
        """Current colours as hex strings, in logical order (left ring, right ring, pupils)."""
        f = (self.leds.logical * 255).round().astype(int)
        return ["#%02x%02x%02x" % tuple(c) for c in f]

    def geometry(self):
        px = self.layout.all
        return [{"x": float(x), "y": float(y), "pupil": bool(p)} for x, y, p in zip(px.x, px.y, px.pupil)]

    # ------------------------------------------------------------------ scenes
    def info(self):
        data = custom.load(self.custom_path)
        return {
            "scenes": [{"name": n, "builtin": n in scenes.BUILTIN, "spec": data["scenes"].get(n)}
                       for n in scenes.SCENES],
            "state_scenes": dict(scenes.STATE_SCENES),
            "default_state_scenes": scenes.BUILTIN_STATE_SCENES,
            "effects": custom.schema(),
            "events": list(EVENTS),
            "talk_targets": list(TALK_TARGETS),
            "geometry": self.geometry(),
        }

    def preview(self, name):
        with self.lock:
            self._need_preview()
            self.scene = scenes.make(name)
            self.scene_name, self.t0, self.overlay = name, self.clock(), None
            if self.scene.gaze is not None:  # nobody to look at: sweep around
                self.scene.gaze.look = (0.8, -0.3)
        self.note(f"Showing scene '{name}'")

    def preview_spec(self, spec):
        """Live preview of an unsaved scene while sliders move. Keeps the animation clock running."""
        try:
            rings, pupils = custom.build(spec)
        except Exception as e:
            raise StudioError(f"That effect setting doesn't work: {e}") from e
        with self.lock:
            self._need_preview()
            self.scene, self.scene_name, self.overlay = scenes.Scene(rings, pupils), "(editing)", None

    def save_scene(self, name, spec):
        name = audio.slug(name)
        if name in scenes.BUILTIN:
            raise StudioError(f"'{name}' is a built-in scene. Pick another name.")
        try:
            custom.build(spec)
        except Exception as e:
            raise StudioError(f"Can't save: {e}") from e
        with self.lock:
            data = custom.load(self.custom_path)
            data["scenes"][name] = {"rings": spec.get("rings", {}), "pupils": spec.get("pupils", {})}
            custom.save(data, self.custom_path)
            scenes.load_custom(self.custom_path)
        self.note(f"Saved scene '{name}'")
        return name

    def delete_scene(self, name):
        if name in scenes.BUILTIN:
            raise StudioError("Built-in scenes can't be deleted.")
        with self.lock:
            data = custom.load(self.custom_path)
            if name not in data["scenes"]:
                raise StudioError(f"No saved scene '{name}'.")
            del data["scenes"][name]
            data["state_scenes"] = {k: v for k, v in data["state_scenes"].items() if v != name}
            custom.save(data, self.custom_path)
            scenes.load_custom(self.custom_path)
        self.note(f"Deleted scene '{name}'")

    def set_state_scene(self, state, name):
        if state not in scenes.BUILTIN_STATE_SCENES:
            raise StudioError(f"Unknown show moment '{state}'.")
        if name not in scenes.SCENES:
            raise StudioError(f"Unknown scene '{name}'.")
        with self.lock:
            data = custom.load(self.custom_path)
            if name == scenes.BUILTIN_STATE_SCENES[state]:
                data["state_scenes"].pop(state, None)
            else:
                data["state_scenes"][state] = name
            custom.save(data, self.custom_path)
            scenes.load_custom(self.custom_path)
        self.note(f"{state} now uses '{name}'")

    # ------------------------------------------------------------------ sounds
    def _safe(self, rel):
        p = (self.sounds_root / rel).resolve()
        if self.sounds_root.resolve() not in p.parents or not p.is_file():
            raise StudioError("That sound file isn't in the library.")
        return p

    def library(self):
        clips = []
        for event in EVENTS:
            for p in sorted((self.sounds_root / event).glob("*")):
                if p.suffix.lower() in audio.SOUND_EXTS:
                    clips.append(self._clip(p, None, event))
        voices = []
        bank = VoiceBank(self.sounds_root / "voices", self.player)
        for v in bank.voices:
            voices.append({"name": v.name, "scene": v.scene, "talk": v.talk, "weight": v.weight})
            for event, files in v.lines.items():
                clips += [self._clip(p, v.name, event) for p in files]
        return {"clips": clips, "voices": voices}

    def _clip(self, path, voice, event):
        entry = {"id": path.relative_to(self.sounds_root).as_posix(), "name": path.name, "voice": voice,
                 "event": event, "placeholder": path.name.startswith("placeholder_")}
        try:
            info = audio.analyse(path)
            entry.update(duration=round(info.duration, 2), peak_db=round(info.peak_db, 1), rms_db=round(info.rms_db, 1),
                         quiet=bool(info.rms_db < -32), clipping=bool(info.peak_db > -0.5))
        except Exception as e:
            entry["error"] = str(e)
        return entry

    def play(self, rel):
        path = self._safe(rel)
        info = audio.analyse(path)
        parts = Path(rel).parts
        voice = load_voice(self.sounds_root / "voices" / parts[1]) if parts[0] == "voices" else None
        event = parts[2] if voice else parts[0]
        state_scene = scenes.STATE_SCENES[EVENT_STATE.get(event, "IDLE")]
        scene = (scenes.talking(Line(voice, event, info), state_scene, self.layout.pupils.n > 0) if voice
                 else scenes.make(state_scene))
        with self.lock:
            if self.show is None:
                now = self.clock()
                self.overlay = (scene, now, now + info.duration + 0.3)
        self.player.play(path)
        self.note(f"Playing {rel}")
        return {"duration": info.duration}

    def stop_sounds(self):
        self.player.stop()
        with self.lock:
            self.overlay = None

    def upload(self, filename, data, event, voice=None, name=None):
        ext = Path(filename).suffix.lower()
        if ext not in UPLOAD_EXTS:
            raise StudioError(f"Can't use {ext or 'that'} files. Try .wav, .mp3, .m4a, .ogg or a video.")
        if len(data) > MAX_UPLOAD:
            raise StudioError("That file is too big (100 MB max). Trim it first.")
        if event not in EVENTS:
            raise StudioError(f"Pick when it plays: {', '.join(EVENTS)}.")
        convert = shutil.which("ffmpeg") is not None
        if not convert and ext not in audio.SOUND_EXTS:
            raise StudioError(f"Can't convert {ext} files here (no ffmpeg). Use .wav, .ogg or .mp3.")
        folder = (self.sounds_root / "voices" / audio.slug(voice) / event) if voice else self.sounds_root / event
        stem = audio.slug(name or Path(filename).stem)
        raw = self.raw_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{stem}{ext}"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(data)  # keep the original
        out_ext = ".ogg" if convert else ext  # without ffmpeg, playable files are used as they are
        dest, i = folder / f"{stem}{out_ext}", 2
        while dest.exists():
            dest, i = folder / f"{stem}_{i}{out_ext}", i + 1
        if convert:
            try:
                audio.prepare(raw, dest)
            except RuntimeError as e:
                raise StudioError(f"Couldn't convert the file: {e}") from e
        else:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(raw, dest)
        self.note(f"Added {dest.relative_to(self.sounds_root).as_posix()}")
        return self._clip(dest, audio.slug(voice) if voice else None, event)

    def delete_clip(self, rel):
        path = self._safe(rel)
        trash = self.sounds_root / ".trash" / rel
        trash.parent.mkdir(parents=True, exist_ok=True)
        path.replace(trash)
        self.note(f"Moved {rel} to sounds/.trash")

    def save_voice(self, name, scene=None, talk="pupils", weight=1.0):
        name = audio.slug(name)
        if scene and scene not in scenes.SCENES:
            raise StudioError(f"Unknown scene '{scene}'.")
        if talk not in TALK_TARGETS:
            raise StudioError(f"'talk' must be one of {', '.join(TALK_TARGETS)}.")
        folder = self.sounds_root / "voices" / name
        folder.mkdir(parents=True, exist_ok=True)
        lines = [f'scene = "{scene}"'] if scene else []
        lines += [f'talk = "{talk}"', f"weight = {float(weight):g}"]
        (folder / "voice.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        tomllib.loads((folder / "voice.toml").read_text(encoding="utf-8"))  # sanity check
        self.note(f"Saved voice '{name}'")
        return name

    # ------------------------------------------------------------------ show
    def _need_preview(self):
        if self.show is not None:
            raise StudioError("The show is running. Stop it first (Show tab).")

    def start_show(self, camera="sim"):
        with self.lock:
            if self.show is not None:
                return
            cfg, root = self.cfg, self.cfg.path(".")
            sim_cam = None
            if camera == "real":
                try:
                    cam = Camera(cfg.camera.index, (cfg.camera.width, cfg.camera.height), cfg.camera.rotate)
                except Exception as e:
                    raise StudioError(f"Camera didn't start: {e}") from e
            else:
                cam = sim_cam = SimCamera.from_captures(cfg.path(cfg.captures))
            watcher = FaceWatcher(cam, FaceDetector(cfg.camera.detect_scale, cfg.camera.min_score))
            if camera == "real" and self.pir is not None:
                inputs = MonitorInputs(self.pir)  # real motion sensors (the button still works too)
            else:
                inputs = SimInputs(sim_cam.toggle_face if sim_cam else None, read_stdin=False)
            aim = SimAim()
            if not cfg.teensy.enabled:  # the aiming LED only exists on the old driver board
                try:
                    aim = AimLed(cfg.pins.aim_led)
                except Exception:
                    pass
            display = FileDisplay(cfg.display, root)
            if cfg.display.backend == "stream":  # also send it to the real display computer
                try:
                    display = StreamDisplay(cfg.display, root)
                    display.watcher = watcher
                except OSError as e:
                    log.warning("display stream unavailable (%s); preview only", e)
            self.show_dev = Devices(
                self.layout, self.leds, inputs,
                aim, SoundBank(self.sounds_root, self.player), display, watcher, sim_cam,
                VoiceBank(self.sounds_root / "voices", self.player, cfg.audio.voice_chance))
            self.show = Show(cfg, self.show_dev, clock=self.clock)
            self.overlay = None
        real = "real camera + sensors" if self.pir is not None else "real camera, pretend sensors"
        self.note(f"Show started ({real if camera == 'real' else 'pretend camera and sensors'})")

    def stop_show(self):
        with self.lock:
            if self.show is None:
                return
            self.show.executor.shutdown(wait=False, cancel_futures=True)
            for d in (self.show_dev.watcher, self.show_dev.aim, self.show_dev.display):
                try:
                    d.close()
                except Exception as e:
                    log.warning("closing %s: %s", type(d).__name__, e)
            self.show = self.show_dev = None
            self.scene, self.t0 = scenes.make(self.scene_name if self.scene_name in scenes.SCENES else "idle"), self.clock()
        self.player.stop()
        self.note("Show stopped")

    def motion(self, sensor=0):
        with self.lock:
            if self.show is None:
                raise StudioError("Start the show first.")
            self.show_dev.inputs.trigger(sensor)
        self.note(f"Pretend PIR {sensor + 1} sees someone")

    def toggle_face(self):
        with self.lock:
            cam = self.show_dev.sim_camera if self.show_dev else None
            if cam is None:
                raise StudioError("Start the show with the pretend camera first.")
            if not cam.faces:
                raise StudioError("No earlier photos to use as a pretend visitor (take one with the real camera).")
            cam.toggle_face()
            on = cam.face_on
        self.note("Pretend face appears" if on else "Pretend face leaves")
        return on

    def status(self):
        with self.lock:
            s = self.show
            disp = self.cfg.path(self.cfg.display.file_path)
            return {
                "mode": "show" if s else "preview",
                "scene": self.scene_name,
                "state": s.state.name if s else None,
                "state_seconds": round(s.elapsed(self.clock()), 1) if s else None,
                "face": bool(self.show_dev and self.show_dev.sim_camera and self.show_dev.sim_camera.face_on),
                "display_version": disp.stat().st_mtime if disp.is_file() else None,
                "pir": self.pir.levels() if self.pir is not None else None,
                "events": list(self.events),
            }

    def pir_scope(self):
        if self.pir is None:
            return {"available": False}
        return self.pir.snapshot()

    def pir_reset(self):
        if self.pir is not None:
            self.pir.reset_stats()

    def display_path(self):
        return self.cfg.path(self.cfg.display.file_path)

"""Builds the hardware, falling back to simulated or null devices.

`sim` is a set of device names to simulate: leds, aim, audio, display, camera, imx
(or "all"). A real device that fails to start is logged and replaced, so the show
keeps running with whatever works. With [teensy] enabled the LEDs go through the
Teensy, and the aiming LED is always simulated.
"""

import logging
from dataclasses import dataclass

from ..layout import Layout
from ..voices import VoiceBank
from .camera import Camera, FaceDetector, FaceWatcher, SimCamera, quiet_opencv
from .display import FileDisplay, NullDisplay, PygameDisplay, StreamDisplay
from .imx import ImxLink, LogImx
from .inputs import SimInputs
from .leds import Leds, NullStrip, SpiStrip, TerminalStrip
from .outputs import AimLed, LogPlayer, PygamePlayer, SimAim, SoundBank
from .teensy import TeensyStrip

log = logging.getLogger(__name__)

DEVICES = ("leds", "aim", "audio", "display", "camera", "imx")


@dataclass
class Devices:
    layout: Layout
    leds: Leds
    inputs: object
    aim: object
    sounds: SoundBank
    display: object
    watcher: FaceWatcher | None
    sim_camera: SimCamera | None = None
    voices: VoiceBank | None = None
    imx: object = None  # animation triggers for the i.MX, or None

    def close(self):
        for d in (self.watcher, self.leds, self.inputs, self.aim, self.sounds, self.display, self.imx):
            if d is not None:
                try:
                    d.close()
                except Exception as e:
                    log.warning("closing %s: %s", type(d).__name__, e)


def _try(name, real, fallback):
    try:
        return real()
    except Exception as e:
        log.warning("%s unavailable (%s); falling back", name, e)
        return fallback()


def open_strip(cfg):
    """The real LED chain: through the Teensy, or straight off the Pi's SPI."""
    if cfg.teensy.enabled:
        return TeensyStrip(cfg.teensy.port)
    return SpiStrip(cfg.leds.spi_bus, cfg.leds.spi_device)


def build(cfg, sim=(), terminal_preview=None):
    sim = set(DEVICES) if "all" in sim else set(sim)
    unknown = sim - set(DEVICES)
    if unknown:
        raise ValueError(f"Unknown device(s) to simulate: {', '.join(sorted(unknown))}")
    quiet_opencv()
    root = cfg.path(".")
    layout = Layout(cfg.leds)

    if terminal_preview is None:
        terminal_preview = "leds" in sim
    preview = lambda: TerminalStrip(layout)  # noqa: E731
    if "leds" in sim:
        strip = preview() if terminal_preview else NullStrip()
    else:
        strip = _try("LEDs", lambda: open_strip(cfg), preview if terminal_preview else NullStrip)
    leds = Leds(layout, strip)

    sim_camera = None
    watcher = None
    if "camera" in sim:
        sim_camera = SimCamera.from_captures(cfg.path(cfg.captures))
        cam = sim_camera
    else:
        cam = _try("camera", lambda: Camera(cfg.camera.index, (cfg.camera.width, cfg.camera.height),
                                            cfg.camera.rotate), lambda: None)
    if cam is not None:
        watcher = FaceWatcher(cam, FaceDetector(cfg.camera.detect_scale, cfg.camera.min_score))

    face_toggle = sim_camera.toggle_face if sim_camera else None
    inputs = SimInputs(face_toggle)  # keyboard walk-ups; the camera is what really wakes the show

    if "aim" in sim or cfg.teensy.enabled:
        aim = SimAim()
    else:
        aim = _try("aiming LED", lambda: AimLed(cfg.pins.aim_led), SimAim)
    player = LogPlayer() if "audio" in sim else _try("audio", lambda: PygamePlayer(cfg.audio.volume), LogPlayer)
    sounds = SoundBank(cfg.path(cfg.audio.folder), player)
    voices = VoiceBank(cfg.path(cfg.audio.folder) / "voices", player, cfg.audio.voice_chance)

    if "display" in sim or cfg.display.backend == "file":
        display = FileDisplay(cfg.display, root)
    elif cfg.display.backend == "stream":
        display = _try("display stream", lambda: StreamDisplay(cfg.display, root), lambda: FileDisplay(cfg.display, root))
    elif cfg.display.backend == "pygame":
        display = _try("display", lambda: PygameDisplay(cfg.display, root), lambda: FileDisplay(cfg.display, root))
    else:
        display = NullDisplay()

    if isinstance(display, StreamDisplay):
        display.watcher = watcher  # live camera preview at :<stream_port>/camera

    imx = None
    if "imx" in sim:
        imx = LogImx()
    elif cfg.imx.host:
        imx = _try("i.MX triggers", lambda: ImxLink(cfg.imx.host, cfg.imx.port), lambda: None)
    return Devices(layout, leds, inputs, aim, sounds, display, watcher, sim_camera, voices, imx)

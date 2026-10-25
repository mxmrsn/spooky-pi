"""Builds the hardware, falling back to simulated or null devices.

`sim` is a set of device names to simulate: leds, pir, aim, audio, display, camera
(or "all"). A real device that fails to start is logged and replaced, so the
show keeps running with whatever works. With [teensy] enabled the LEDs and PIRs
go through the Teensy, and the aiming LED is always simulated.
"""

import logging
from dataclasses import dataclass

from ..layout import Layout
from ..voices import VoiceBank
from .camera import Camera, FaceDetector, FaceWatcher, SimCamera, quiet_opencv
from .display import FileDisplay, NullDisplay, PygameDisplay, StreamDisplay
from .inputs import PirSensors, SimInputs
from .leds import Leds, NullStrip, SpiStrip, TerminalStrip
from .outputs import AimLed, LogPlayer, PygamePlayer, SimAim, SoundBank
from .teensy import TeensyInput, TeensyStrip

log = logging.getLogger(__name__)

DEVICES = ("leds", "pir", "aim", "audio", "display", "camera")


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

    def close(self):
        for d in (self.watcher, self.leds, self.inputs, self.aim, self.sounds, self.display):
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


def open_pirs(cfg):
    """(labels, devices) for the real PIR sensors: the Teensy's inputs or Pi GPIO pins."""
    if cfg.teensy.enabled:
        pins = list(cfg.teensy.pir_pins)
        return pins, [TeensyInput(i, cfg.teensy.port) for i in range(len(pins))]
    from gpiozero import DigitalInputDevice
    return list(cfg.pins.pir), [DigitalInputDevice(p, pull_up=False) for p in cfg.pins.pir]


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
    pir_pins = cfg.teensy.pir_pins if cfg.teensy.enabled else cfg.pins.pir
    if "pir" in sim or not pir_pins:
        inputs = SimInputs(face_toggle)
    else:
        inputs = _try("PIR sensors", lambda: PirSensors(open_pirs(cfg)[1]), lambda: SimInputs(face_toggle))

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
    return Devices(layout, leds, inputs, aim, sounds, display, watcher, sim_camera, voices)

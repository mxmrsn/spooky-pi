"""Settings for the whole installation.

Defaults live here. Override any of them in a `spooky.toml` next to this package
(see spooky.example.toml), e.g.

    [leds]
    brightness = 0.3
    ring_offset = [4, 12]
"""

import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Pins:
    # Pi GPIO, used only when [teensy] enabled = false (the driver board in hardware/BOM.md)
    pir: tuple = (23, 24)  # BCM numbers; first is the sensor on the glasses' left as seen from the front
    aim_led: int = 17
    # NeoPixel data is SPI0 MOSI (GPIO10), selected by LedConfig.spi_bus/spi_device


@dataclass
class TeensyConfig:
    # The LEDs and PIRs hang off a Teensy 4.1 on USB (firmware: teensy/). No aiming LED in this build.
    enabled: bool = True
    port: str = ""  # serial device; empty finds /dev/serial/by-id/*Teensyduino*
    # Teensy pins with PIRs, as set in the firmware (2, 3); first is the glasses' left sensor.
    # None fitted for now: a face in the camera wakes the show ([show] wake_on_face).
    pir_pins: tuple = ()


@dataclass
class LedConfig:
    # Order of the segments along the data line, starting at the Teensy. The pupils are optional
    # (not fitted for now); with them: left_ring, left_pupil, right_ring, right_pupil.
    chain: list = field(default_factory=lambda: [["left_ring", 16], ["right_ring", 16]])
    # Physical index (within each ring) of the pixel at 12 o'clock, seen from the front: [left, right]
    ring_offset: list = field(default_factory=lambda: [0, 0])
    # Does the index increase clockwise, seen from the front? [left, right]
    ring_clockwise: list = field(default_factory=lambda: [True, True])
    brightness: float = 0.4  # global cap, 0..1
    gamma: float = 2.2
    max_current_a: float = 2.0  # estimated LED current budget: 2.5 A USB brick minus Teensy, PIRs, level shifter
    fps: int = 50
    spi_bus: int = 0
    spi_device: int = 0


@dataclass
class CameraConfig:
    index: int = 0
    width: int = 1920
    height: int = 1080
    rotate: str = "ccw"  # none | cw | ccw | 180
    detect_scale: float = 1 / 3
    min_score: float = 0.7
    # Flip the gaze direction if the eyes look away from visitors instead of at them
    gaze_mirror: bool = True


@dataclass
class ShowConfig:
    wake_on_face: bool = True  # the camera watches while idle, and a face wakes the show (no PIRs needed)
    wake_face_hold: float = 0.5  # a face must stay this long to wake it (skips one-frame false detections)
    awaken_time: float = 1.0  # after a face wakes it, the eyes wake up this long before "spotted"
    awake_timeout: float = 20.0  # back to idle if no face appears for this long
    # From lock-on to photo: face_hold + countdown = 5 s with the face in view the whole time
    face_hold: float = 2.0  # lock-on: eyes follow the face this long before the countdown
    hold_still_after: float = 1.0  # "hold still!" cue + on-screen prompt this far into the lock-on
    close_enough: float = 0.18  # on-screen "Step closer" while the face is narrower than this share of the frame
    face_lost_grace: float = 1.5  # countdown aborts if the face is gone this long
    countdown: float = 3.0
    flash: float = 0.25
    reveal: float = 2.5  # strobe + scream after the photo appears
    display_seconds: float = 12.5  # before/after stays up reveal + display_seconds = 15 s
    rearm: float = 6.0  # ignore motion this long after a photo, so one visitor isn't snapped twice
    ambient_interval: list = field(default_factory=lambda: [45.0, 120.0])  # idle cackle every N..M s
    save_photos: bool = True
    keep_photos: int = 1000  # older captures are deleted (~1 MB per photo + scary version)
    grin: float = 1.0
    eyes: float = 0.3


@dataclass
class AudioConfig:
    folder: str = "sounds"
    volume: float = 1.0
    # Chance a character voice (sounds/voices/*) speaks on each show event, if it has lines for it
    voice_chance: dict = field(default_factory=lambda: {
        "ambient": 1.0, "awaken": 0.7, "spotted": 0.8, "hold_still": 1.0, "countdown": 0.0,
        "shutter": 0.0, "scream": 0.6, "outro": 0.8})


@dataclass
class DisplayConfig:
    backend: str = "stream"  # stream (to the i.MX 8M Plus over Ethernet) | pygame | file | none
    size: list = field(default_factory=lambda: [1920, 1080])  # display resolution (stream/file backends)
    stream_port: int = 8090  # http://<pi>:8090/stream.mjpg for the display computer
    rotate: int = 0  # degrees clockwise applied to everything shown
    idle_image: str = "media/idle.jpg"  # optional attract screen
    file_path: str = "captures/display.jpg"  # used by the file backend


@dataclass
class Config:
    pins: Pins = field(default_factory=Pins)
    teensy: TeensyConfig = field(default_factory=TeensyConfig)
    leds: LedConfig = field(default_factory=LedConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    show: ShowConfig = field(default_factory=ShowConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    captures: str = "captures"

    def path(self, p):
        """Resolve a config path relative to the project root."""
        p = Path(p)
        return p if p.is_absolute() else ROOT / p


def _merge(obj, data, where):
    names = {f.name for f in fields(obj)}
    for key, value in data.items():
        if key not in names:
            raise ValueError(f"Unknown setting {where}{key}")
        current = getattr(obj, key)
        if is_dataclass(current):
            _merge(current, value, f"{where}{key}.")
        elif isinstance(current, dict):
            current.update(value)
        else:
            setattr(obj, key, type(current)(value) if isinstance(current, tuple) else value)


def load(path=None):
    cfg = Config()
    path = Path(path) if path else ROOT / "spooky.toml"
    if path.is_file():
        with open(path, "rb") as f:
            _merge(cfg, tomllib.load(f), "")
    return cfg

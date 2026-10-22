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
    pir: tuple = (23, 24)  # BCM numbers; first is the sensor on the glasses' left as seen from the front
    aim_led: int = 17
    # NeoPixel data is SPI0 MOSI (GPIO10), selected by LedConfig.spi_bus/spi_device


@dataclass
class LedConfig:
    # Order of the segments along the data line, starting at the Pi.
    chain: list = field(default_factory=lambda: [
        ["left_ring", 16], ["left_pupil", 1], ["right_ring", 16], ["right_pupil", 1]])
    # Physical index (within each ring) of the pixel at 12 o'clock, seen from the front: [left, right]
    ring_offset: list = field(default_factory=lambda: [0, 0])
    # Does the index increase clockwise, seen from the front? [left, right]
    ring_clockwise: list = field(default_factory=lambda: [True, True])
    brightness: float = 0.4  # global cap, 0..1
    gamma: float = 2.2
    max_current_a: float = 1.5  # estimated LED current budget for the USB brick
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
    awake_timeout: float = 20.0  # back to idle if no face appears for this long
    face_hold: float = 1.5  # eyes follow the face this long before the countdown starts
    face_lost_grace: float = 1.5  # countdown aborts if the face is gone this long
    countdown: float = 3.0
    flash: float = 0.25
    reveal: float = 2.5  # strobe + scream after the photo appears
    display_seconds: float = 12.0  # how long the scary photo stays up
    rearm: float = 6.0  # ignore motion this long after a photo, so one visitor isn't snapped twice
    ambient_interval: list = field(default_factory=lambda: [45.0, 120.0])  # idle cackle every N..M s
    save_photos: bool = True
    keep_photos: int = 50  # older captures are deleted
    grin: float = 1.0
    eyes: float = 0.3


@dataclass
class AudioConfig:
    folder: str = "sounds"
    volume: float = 1.0


@dataclass
class DisplayConfig:
    backend: str = "pygame"  # pygame | file | none
    rotate: int = 0  # degrees clockwise applied to everything shown
    idle_image: str = "media/idle.jpg"  # optional attract screen
    file_path: str = "captures/display.jpg"  # used by the file backend


@dataclass
class Config:
    pins: Pins = field(default_factory=Pins)
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
        else:
            setattr(obj, key, type(current)(value) if isinstance(current, tuple) else value)


def load(path=None):
    cfg = Config()
    path = Path(path) if path else ROOT / "spooky.toml"
    if path.is_file():
        with open(path, "rb") as f:
            _merge(cfg, tomllib.load(f), "")
    return cfg

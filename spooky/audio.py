"""Audio file analysis: duration, levels and a loudness envelope for the talking LEDs.

WAV is read directly; other formats (ogg, mp3, m4a...) are decoded with ffmpeg
when it is installed (it is on the Pi).
"""

import re
import shutil
import subprocess
import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

ENVELOPE_HZ = 50
SOUND_EXTS = {".wav", ".ogg", ".mp3"}  # what pygame can play; tools/prep_audio.py converts anything else
DECODE_RATE = 22050


@dataclass
class ClipInfo:
    path: Path
    duration: float
    peak_db: float
    rms_db: float
    envelope: np.ndarray  # 0..1 loudness at ENVELOPE_HZ, normalised to the clip's loud parts


def _read_wav(path):
    with wave.open(str(path), "rb") as w:
        rate, width, channels = w.getframerate(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(w.getnframes())
    if width == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
    elif width == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        x = ((b[:, 0].astype(np.int32) | b[:, 1].astype(np.int32) << 8 | b[:, 2].astype(np.int32) << 16)
             << 8 >> 8).astype(np.float32) / 8388608
    elif width == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648
    else:
        raise ValueError(f"Unsupported WAV sample width {width}")
    return x.reshape(-1, channels).mean(axis=1), rate


def _read_ffmpeg(path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(f"ffmpeg is needed to read {Path(path).suffix} files")
    out = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(DECODE_RATE),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, "<i2").astype(np.float32) / 32768, DECODE_RATE


def load(path):
    """Mono float samples in -1..1 and the sample rate."""
    path = Path(path)
    return _read_wav(path) if path.suffix.lower() == ".wav" else _read_ffmpeg(path)


def _db(x):
    return float(20 * np.log10(max(float(x), 1e-6)))


@lru_cache(maxsize=256)
def _analyse(path, mtime):
    x, rate = load(path)
    duration = len(x) / rate
    hop = max(1, rate // ENVELOPE_HZ)
    n = max(1, len(x) // hop)
    frames = x[:n * hop].reshape(n, hop) if len(x) >= hop else np.pad(x, (0, hop - len(x)))[None]
    rms = np.sqrt((frames ** 2).mean(axis=1))
    loud = np.percentile(rms, 95) if rms.size else 0.0
    env = np.clip(rms / loud, 0, 1) if loud > 1e-4 else np.zeros_like(rms)
    return ClipInfo(Path(path), duration, _db(np.abs(x).max() if x.size else 0),
                    _db(np.sqrt((x ** 2).mean()) if x.size else 0), env.astype(np.float32))


def analyse(path):
    """Cached per file version, so edits to a clip are picked up."""
    p = Path(path)
    return _analyse(str(p), p.stat().st_mtime)


def slug(name):
    """Safe file/folder name: lowercase letters, digits and underscores."""
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_") or "clip"


_SILENCE = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05"
TRIM = f"{_SILENCE},areverse,{_SILENCE},areverse"  # trim the start, then the (reversed) end
NORMALISE = "loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:d=0.01"


def prepare(src, dest, start=None, end=None, trim=True):
    """Any audio/video file -> show-ready mono 44.1 kHz .ogg at dest: silence trimmed,
    loudness evened out (EBU R128, -16 LUFS). Needs ffmpeg. Raises RuntimeError on failure."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found (it is on the Pi; elsewhere install it)")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", str(src), "-vn", "-af", f"{TRIM},{NORMALISE}" if trim else NORMALISE,
            "-ac", "1", "-ar", "44100", "-c:a", "libvorbis", "-q:a", "6", str(dest)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or not dest.is_file():
        raise RuntimeError(r.stderr.strip() or "ffmpeg failed")
    return dest


def write_wav(path, samples, rate=44100):
    """Write mono float samples (-1..1) as 16-bit WAV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data)

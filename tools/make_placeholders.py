"""Generate synthetic placeholder clips so the sound + LED pipeline can be tested
before the real recordings exist.

    python tools/make_placeholders.py           sfx for every event + two fake bosses
    python tools/make_placeholders.py --clean   delete all placeholder_* files again

Voices babble in a speech-like rhythm (so the talking LEDs have something to follow):
boss_a is low and slow, boss_b high and fast. Real files can sit alongside these;
run --clean once they are in.
"""

import argparse
import zlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from spooky import config  # noqa: E402
from spooky.audio import write_wav  # noqa: E402

RATE = 44100
rng = np.random.default_rng(13)


def t_axis(seconds):
    return np.arange(int(seconds * RATE)) / RATE


def env(n, attack=0.01, release=0.1):
    e = np.ones(n)
    a, r = int(attack * RATE), int(release * RATE)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def sweep(f0, f1, seconds, shape="sine"):
    t = t_axis(seconds)
    f = np.geomspace(f0, f1, len(t))
    phase = 2 * np.pi * np.cumsum(f) / RATE
    return np.sin(phase) if shape == "sine" else 2 * (phase / (2 * np.pi) % 1) - 1


def norm(x, peak=0.7):
    return x / max(np.abs(x).max(), 1e-9) * peak


def sfx():
    out = {}
    t = t_axis(6)
    out["ambient"] = norm((np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 82.5 * t * (1 + 0.01 * np.sin(t))))
                          * (0.6 + 0.4 * np.sin(2 * np.pi * 0.3 * t)) * env(len(t), 1.0, 1.5), 0.4)
    out["awaken"] = norm(sweep(80, 600, 1.2, "saw") * env(int(1.2 * RATE), 0.05, 0.3))
    beeps = [np.r_[np.sin(2 * np.pi * f * t_axis(0.18)) * env(int(0.18 * RATE), 0.005, 0.05), np.zeros(int(0.82 * RATE))]
             for f in (440, 440, 880)]
    out["countdown"] = norm(np.concatenate(beeps))
    n = int(0.15 * RATE)
    out["shutter"] = norm(rng.standard_normal(n) * np.exp(-np.arange(n) / (0.02 * RATE)))
    s = sweep(1400, 300, 1.6, "saw") + 0.6 * rng.standard_normal(int(1.6 * RATE))
    out["scream"] = norm(s * env(len(s), 0.02, 0.5))
    out["spotted"] = norm(np.r_[sweep(220, 220, 0.15), sweep(233, 233, 0.5)] * env(int(0.65 * RATE), 0.01, 0.3))
    pulses = np.concatenate([sweep(300 - 30 * i, 280 - 30 * i, 0.14, "saw") * env(int(0.14 * RATE), 0.01, 0.06)
                             for i in range(6)])
    out["outro"] = norm(pulses)
    tick = np.r_[np.sin(2 * np.pi * 1200 * t_axis(0.03)), np.zeros(int(0.17 * RATE))]
    out["hold_still"] = norm(np.tile(tick, 5) + 0.4 * sweep(200, 800, len(tick) * 5 / RATE))
    return out


def babble(seconds, f0, rate_hz, seed):
    """Speech-like noise: voiced 'syllables' with pitch drift and formants, in words with pauses."""
    r = np.random.default_rng(seed)
    pieces = []
    total = 0.0
    while total < seconds:
        for _ in range(r.integers(1, 4)):  # syllables per word
            d = r.uniform(0.6, 1.4) / rate_hz
            t = t_axis(d)
            pitch = f0 * (1 + 0.15 * r.standard_normal()) * np.linspace(1.1, 0.9, len(t))
            phase = 2 * np.pi * np.cumsum(pitch) / RATE
            formant1, formant2 = r.uniform(300, 800), r.uniform(900, 2200)
            voice = sum(np.sin(k * phase) * (np.exp(-((k * f0 - formant1) / 250) ** 2) +
                                             0.6 * np.exp(-((k * f0 - formant2) / 400) ** 2) + 0.05)
                        for k in range(1, 30))
            pieces.append(voice * np.sin(np.pi * np.linspace(0, 1, len(t))) ** 0.7)
            total += d
        gap = r.uniform(0.08, 0.35)
        pieces.append(np.zeros(int(gap * RATE)))
        total += gap
    return norm(np.concatenate(pieces), 0.6)


VOICES = {
    # name: (pitch Hz, syllables/s, voice.toml contents)
    "boss_a": (95, 3.5, 'scene = "glare"\ntalk = "pupils"\nweight = 1.0\n'),
    "boss_b": (165, 5.5, 'scene = "rage"\ntalk = "all"\nweight = 1.0\n'),
}
VOICE_LINES = {"ambient": 3.0, "awaken": 1.5, "spotted": 2.0, "hold_still": 1.0, "scream": 1.2, "outro": 2.5}


def main():
    ap = argparse.ArgumentParser(description="Create or remove placeholder sound clips.")
    ap.add_argument("--clean", action="store_true", help="delete placeholder_* files")
    args = ap.parse_args()
    cfg = config.load()
    root = cfg.path(cfg.audio.folder)

    if args.clean:
        files = list(root.rglob("placeholder_*.wav"))
        for f in files:
            f.unlink()
        print(f"Removed {len(files)} placeholder clips.")
        return

    count = 0
    for event, x in sfx().items():
        write_wav(root / event / "placeholder_1.wav", x, RATE)
        count += 1
    for name, (f0, syl, toml) in VOICES.items():
        folder = root / "voices" / name
        for i, (event, seconds) in enumerate(VOICE_LINES.items()):
            for take in (1, 2):
                write_wav(folder / event / f"placeholder_{take}.wav",
                          babble(seconds * (0.8 + 0.4 * take / 2), f0, syl, zlib.crc32(f"{name}{event}{take}".encode())), RATE)
                count += 1
        settings = folder / "voice.toml"
        if not settings.exists():
            settings.write_text(toml)
    print(f"Wrote {count} placeholder clips under {root}.")


if __name__ == "__main__":
    main()

"""Try out sounds and voices together with their LED animations.

    python -m spooky.audition list                         every clip, its length and level warnings
    python -m spooky.audition play boss_a                  each of boss_a's lines with its talking scene
    python -m spooky.audition play boss_a --event scream   just one event
    python -m spooky.audition play sfx --event countdown   plain sound effects with their state's scene
    python -m spooky.audition state REVEAL --times 3       enter a show state 3 times: same cues as the show
    python -m spooky.audition state AWAKE --voice boss_b   ...with only boss_b talking

Add --sim to draw the LEDs in the terminal, --mute to skip audio playback.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from . import audio, config, hw, scenes
from .hw import open_strip
from .hw.leds import Leds, TerminalStrip
from .audio import SOUND_EXTS
from .hw.outputs import LogPlayer, PygamePlayer
from .layout import Layout
from .show import Show, State
from .voices import EVENTS, Line, VoiceBank

EVENT_STATE = {"ambient": "IDLE", "awaken": "AWAKE", "spotted": "WATCHING", "hold_still": "WATCHING",
               "countdown": "COUNTDOWN", "shutter": "CAPTURE", "scream": "REVEAL", "outro": "SHOWING"}


# ---------------------------------------------------------------------- library check
def library_report(cfg):
    """[(source, event, file, ClipInfo | None, [problems], [warnings])] for every clip, plus voice setup issues."""
    root = cfg.path(cfg.audio.folder)
    rows = []

    def check(source, event, path):
        problems, warnings = [], []
        info = None
        try:
            info = audio.analyse(path)
        except Exception as e:
            problems.append(f"unreadable: {e}")
        if info is not None:
            if info.duration < 0.05:
                problems.append("empty")
            if info.peak_db > -0.5:
                warnings.append("clipping?")
            if info.rms_db < -32:
                warnings.append("quiet")
            if event == "countdown" and info.duration > cfg.show.countdown + 0.5:
                warnings.append(f"longer than the {cfg.show.countdown:g} s countdown")
            if event != "ambient" and info.duration > 10:
                warnings.append("long")
        rows.append((source, event, Path(path).name, info, problems, warnings))

    for event in EVENTS:
        for p in sorted((root / event).glob("*")):
            if p.suffix.lower() in SOUND_EXTS:
                check("sfx", event, p)
    bank = VoiceBank(root / "voices", LogPlayer())
    for v in bank.voices:
        if v.scene and v.scene not in scenes.SCENES:
            rows.append((v.name, "-", "voice.toml", None, [f"unknown scene {v.scene!r}"], []))
        for sub in sorted(p for p in v.folder.iterdir() if p.is_dir() and p.name not in EVENTS):
            rows.append((v.name, sub.name, "", None, [f"unknown event folder (use {', '.join(EVENTS)})"], []))
        for event, files in v.lines.items():
            for p in files:
                check(v.name, event, p)
    return rows


def cmd_list(cfg, args):
    rows = library_report(cfg)
    if not rows:
        print(f"No clips yet. Put files in {cfg.audio.folder}/<event>/ or {cfg.audio.folder}/voices/<name>/<event>/")
        print("(tools/make_placeholders.py creates test clips.)")
        return 0
    print(f"{'source':<12} {'event':<10} {'file':<34} {'len':>6} {'peak':>6} {'rms':>6}  notes")
    for source, event, name, info, problems, warnings in rows:
        nums = f"{info.duration:5.1f}s {info.peak_db:5.1f} {info.rms_db:5.1f}" if info else " " * 20
        print(f"{source:<12} {event:<10} {name[:34]:<34} {nums}  {'; '.join(problems + warnings)}")
    bad = sum(bool(r[4]) for r in rows)
    print(f"\n{len(rows)} entries, {bad} with problems. Levels in dBFS; aim for rms around -20.")
    return 1 if bad else 0


# ---------------------------------------------------------------------- playback
def _leds(cfg, sim):
    layout = Layout(cfg.leds)
    if sim:
        return Leds(layout, TerminalStrip(layout))
    try:
        return Leds(layout, open_strip(cfg))
    except Exception as e:
        print(f"LEDs unavailable ({e}); drawing in the terminal", file=sys.stderr)
        return Leds(layout, TerminalStrip(layout))


def _animate(leds, scene, seconds, label):
    t0 = time.monotonic()
    while (t := time.monotonic() - t0) < seconds:
        leds.show(scene.render(t, leds.layout))
        leds.set_status(f"{label}  {t:4.1f}/{seconds:.1f} s")
        time.sleep(0.02)


def cmd_play(cfg, args):
    root = cfg.path(cfg.audio.folder)
    player = LogPlayer() if args.mute else PygamePlayer(cfg.audio.volume)
    clips = []  # (label, event, path, voice or None)
    if args.source == "sfx":
        for event in EVENTS:
            for p in sorted((root / event).glob("*")):
                if p.suffix.lower() in SOUND_EXTS:
                    clips.append((f"sfx/{event}", event, p, None))
    else:
        bank = VoiceBank(root / "voices", player)
        voice = next((v for v in bank.voices if v.name == args.source), None)
        if voice is None:
            names = ", ".join(v.name for v in bank.voices) or "none yet"
            print(f"No voice {args.source!r}. Voices: {names}; or use 'sfx'.")
            return 1
        for event, files in voice.lines.items():
            clips += [(f"{voice.name}/{event}", event, p, voice) for p in files]
    clips = [c for c in clips if (not args.event or c[1] == args.event) and args.clip.lower() in c[2].name.lower()]
    if not clips:
        print("Nothing matches.")
        return 1
    leds = _leds(cfg, args.sim)
    try:
        for label, event, path, voice in clips:
            info = audio.analyse(path)
            state_scene = scenes.STATE_SCENES[EVENT_STATE[event]]
            scene = (scenes.talking(Line(voice, event, info), state_scene, leds.layout.pupils.n > 0) if voice
                     else scenes.make(state_scene))
            print(f"> {label}/{path.name}  {info.duration:.1f} s")
            player.play(path)
            _animate(leds, scene, info.duration + args.gap, f"{label}/{path.name}")
    except KeyboardInterrupt:
        pass
    finally:
        leds.close()
        player.close()
    return 0


def cmd_state(cfg, args):
    state = State[args.state.upper()]
    sim = {"camera", "display", "aim", "imx"} | ({"leds"} if args.sim else set()) | ({"audio"} if args.mute else set())
    dev = hw.build(cfg, sim)
    if args.voice:
        dev.voices.only = args.voice
    show = Show(cfg, dev)
    show.force_voice = True
    try:
        for i in range(args.times):
            now = time.monotonic()
            show.overlay = None
            dev.voices.busy_until = -1e9
            show._enter(state, now)
            end = max(now + args.seconds, show.overlay[2] if show.overlay else 0)
            while (now := time.monotonic()) < end:
                show.render(now)
                dev.leds.set_status(f"{state.name} #{i + 1}/{args.times}  {now - show.entered:4.1f} s")
                time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        dev.close()
    return 0


def main():
    ap = argparse.ArgumentParser(prog="spooky.audition", description="Audition sounds, voices and LED scenes.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list clips with lengths, levels and warnings")
    p = sub.add_parser("play", help="play clips of one voice (or 'sfx') with their LED scenes")
    p.add_argument("source", help="voice name, or 'sfx' for plain sound effects")
    p.add_argument("--event", choices=EVENTS)
    p.add_argument("--clip", default="", help="only files whose name contains this")
    p.add_argument("--gap", type=float, default=0.8, help="pause after each clip, s")
    s = sub.add_parser("state", help="enter a show state repeatedly, with the show's own cues")
    s.add_argument("state", choices=[st.name for st in State], type=str.upper)
    s.add_argument("--times", type=int, default=3)
    s.add_argument("--seconds", type=float, default=4.0, help="minimum time per repeat")
    s.add_argument("--voice", help="only this voice talks")
    for q in (p, s):
        q.add_argument("--sim", action="store_true", help="draw LEDs in the terminal")
        q.add_argument("--mute", action="store_true", help="don't play audio")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    cfg = config.load()
    sys.exit({"list": cmd_list, "play": cmd_play, "state": cmd_state}[args.cmd](cfg, args))


if __name__ == "__main__":
    main()

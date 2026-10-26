"""Turn raw recordings (phone memos, clips cut from videos...) into show-ready files.

Trims silence at both ends, evens out loudness (EBU R128, -16 LUFS), converts to
44.1 kHz mono .ogg and files each clip in the right folder. Needs ffmpeg (on the Pi).
The Studio's upload button does the same thing.

    python -m spooky.tools.prep_audio raw/*.m4a --voice boss_a --event spotted
    python -m spooky.tools.prep_audio laugh.wav --event ambient           # plain sfx, no voice
    python -m spooky.tools.prep_audio take3.mp3 --voice boss_b --event scream --start 1.2 --end 3.4

Then check them with:  python -m spooky.audition list
"""

import argparse
import sys
from pathlib import Path

from .. import audio, config
from ..voices import EVENTS


def main():
    ap = argparse.ArgumentParser(description="Trim, normalise and file recordings for the show.")
    ap.add_argument("inputs", nargs="+", help="audio or video files in any format ffmpeg reads")
    ap.add_argument("--event", required=True, choices=EVENTS)
    ap.add_argument("--voice", help="character folder under sounds/voices/ (omit for plain sfx)")
    ap.add_argument("--start", type=float, help="cut from this time, s (single input)")
    ap.add_argument("--end", type=float, help="cut up to this time, s (single input)")
    ap.add_argument("--name", help="output file name without extension (single input)")
    ap.add_argument("--keep-silence", action="store_true", help="don't trim silence")
    args = ap.parse_args()
    if len(args.inputs) > 1 and (args.start or args.end or args.name):
        sys.exit("--start/--end/--name work with a single input")

    cfg = config.load()
    root = cfg.path(cfg.audio.folder)
    folder = root / "voices" / args.voice / args.event if args.voice else root / args.event
    failed = 0
    for src in map(Path, args.inputs):
        out = folder / f"{audio.slug(args.name or src.stem)}.ogg"
        try:
            audio.prepare(src, out, args.start, args.end, trim=not args.keep_silence)
            print(f"{src.name} -> {out.relative_to(root.parent)}")
        except RuntimeError as e:
            failed += 1
            print(f"FAILED {src.name}: {e}", file=sys.stderr)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

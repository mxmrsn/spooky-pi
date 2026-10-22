"""Bridge to the ScarySmile script, run on in-memory frames."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ScarySmile"))
import scary_smile as ss  # noqa: E402

MODEL = ss.MODEL


def scare(frame, grin=1.0, eyes=0.3):
    """Return (scary image, number of faces warped). The input frame is not modified."""
    img = frame.copy()
    warps = [ss.FaceWarp(f, grin, eyes) for f in ss.detect_faces(img)]
    for fw in warps:
        fw.apply(img)
    img = ss.horror_grade(img)
    for fw in warps:
        fw.hollow_eyes(img)
    return img, len(warps)

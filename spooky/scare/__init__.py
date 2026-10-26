"""The scary-smile effect (scary_smile.py), run on in-memory frames.

The same effect works on photo files from the command line: python -m spooky.scare photo.jpg
"""

from . import scary_smile as ss

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

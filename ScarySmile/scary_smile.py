"""Scary Smile: a static take on Snapchat's scary smile lens.

Stretches the mouth into an unnaturally wide grin, enlarges and hollows the eyes,
and applies a horror colour grade. Runs fully offline using OpenCV's YuNet face
detector (model file kept next to this script).

Usage:
    python scary_smile.py photo.jpg [more.jpg | folder ...] [-o out.png]
                          [--grin 1.0] [--eyes 0.3] [--no-hollow] [--no-grade]
"""

import argparse
import math
import sys
from pathlib import Path

import cv2
import numpy as np

MODEL = Path(__file__).with_name("face_detection_yunet_2023mar.onnx")
DETECT_MAX_DIM = 2000
IMAGE_EXTS ={".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def detect_faces(img):
    """Return a list of YuNet rows (box, 5 landmarks, score) in full-resolution pixels."""
    h, w = img.shape[:2]
    k = min(1.0, DETECT_MAX_DIM / max(w, h))
    small = cv2.resize(img, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA) if k < 1.0 else img
    sh, sw = small.shape[:2]
    det = cv2.FaceDetectorYN.create(str(MODEL), "", (sw, sh), 0.7, 0.3, 50)
    _, faces = det.detect(small)
    if faces is None:
        return []
    return [f[:14] / k for f in faces]


class FaceWarp:
    """Grin warp plus eye bulges for one face, all as a backward map so every
    output pixel samples a source pixel.

    The grin works in mouth-aligned coordinates (u along the eye line, v up the
    face). The mouth is stretched sideways by up to 1 + 0.9 * grin and its
    corners are curved upwards into the cheeks.
    """

    def __init__(self, f, grin, eyes):
        x, y, bw, bh = f[:4]
        self.W = W = float(bw)
        e1, e2 = np.array(f[4:6], np.float64), np.array(f[6:8], np.float64)
        m1, m2 = np.array(f[10:12], np.float64), np.array(f[12:14], np.float64)
        if e1[0] > e2[0]:
            e1, e2 = e2, e1
        ax = (e2 - e1) / max(np.linalg.norm(e2 - e1), 1e-6)
        self.ax = ax
        self.up = np.array([ax[1], -ax[0]])
        self.mid = (m1 + m2) / 2
        half = max(abs(np.dot(m2 - m1, ax)) / 2, 0.05 * W)
        self.reach = half * (1 + 0.9 * grin)  # half-width of the stretched mouth
        self.stretch = 0.9 * grin
        self.lift = 0.12 * W * grin
        self.eyes = [(e[0], e[1], 0.16 * W, eyes) for e in (e1, e2)]
        pad = 0.4 * W
        self.box = (x - pad, y - pad, x + bw + pad, y + bh + pad)

    def source_maps(self, px, py):
        """Backward map: output pixel grid to source coordinates."""
        W = self.W
        # Undo the eye bulge (it is applied last). The grin barely moves the eyes.
        for ex, ey, R, a in self.eyes:
            dx, dy = px - ex, py - ey
            d2 = dx * dx + dy * dy
            s = np.where(d2 < R * R, 1.0 - a * (1.0 - d2 / (R * R)), 1.0)
            px, py = ex + dx * s, ey + dy * s
        rx, ry = px - self.mid[0], py - self.mid[1]
        u = rx * self.ax[0] + ry * self.ax[1]
        v = rx * self.up[0] + ry * self.up[1]
        # Fades the effect out past the stretched corners
        beyond = np.maximum(np.abs(u) - self.reach, 0.0)
        fu = np.exp(-(beyond / (0.10 * W)) ** 2)
        # Undo the upward curve. Sigma 0.18W keeps it fold-free up to grin 1.5.
        curve = self.lift * np.minimum((u / self.reach) ** 2, 1.0) * fu
        v_s = v - curve * np.exp(-((v - curve) / (0.18 * W)) ** 2)
        # Undo the sideways stretch, strongest on the mouth line
        k = 1.0 + self.stretch * fu * np.exp(-(v_s / (0.12 * W)) ** 2)
        u_s = u / k
        sx = self.mid[0] + u_s * self.ax[0] + v_s * self.up[0]
        sy = self.mid[1] + u_s * self.ax[1] + v_s * self.up[1]
        return sx.astype(np.float32), sy.astype(np.float32)

    def apply(self, img):
        h, w = img.shape[:2]
        x0, y0, x1, y1 = self.box
        x0, y0 = max(0, int(x0)), max(0, int(y0))
        x1, y1 = min(w, int(math.ceil(x1))), min(h, int(math.ceil(y1)))
        if x1 <= x0 or y1 <= y0:
            return
        gx, gy = np.meshgrid(np.arange(x0, x1, dtype=np.float64), np.arange(y0, y1, dtype=np.float64))
        mx, my = self.source_maps(gx, gy)
        img[y0:y1, x0:x1] = cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    def hollow_eyes(self, img):
        W = self.W
        angle = math.degrees(math.atan2(self.ax[1], self.ax[0]))
        mask = np.zeros(img.shape[:2], np.float32)
        for ex, ey, R, a in self.eyes:
            mag = 1.0 / max(1.0 - a, 0.2)
            axes = (max(1, round(0.09 * W * mag)), max(1, round(0.04 * W * mag)))
            cv2.ellipse(mask, (round(ex), round(ey)), axes, angle, 0, 360, 1.0, -1, cv2.LINE_AA)
        k = max(3, int(W * 0.02) | 1)
        mask = cv2.GaussianBlur(mask, (k, k), 0)
        img[:] = (img * (1.0 - mask[..., None])).astype(np.uint8)
        for ex, ey, R, a in self.eyes:
            cv2.circle(img, (round(ex), round(ey)), max(1, round(W * 0.006)), (230, 230, 230), -1, cv2.LINE_AA)


def horror_grade(img):
    """Desaturate, raise contrast, cold green tint and a heavy vignette."""
    f = img.astype(np.float32)
    b, g, r = f[..., 0], f[..., 1], f[..., 2]
    lum = 0.114 * b + 0.587 * g + 0.299 * r
    f = lum[..., None] + (f - lum[..., None]) * 0.35
    f = (f - 128.0) * 1.25 + np.array([124.0, 126.0, 118.0], np.float32)
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2, h / 2
    v = 1.0 - 0.75 * (((xx - cx) ** 2 + (yy - cy) ** 2) / (cx * cx + cy * cy)) ** 1.3
    return np.clip(f * v[..., None], 0, 255).astype(np.uint8)


def process(path, out_path, args):
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        print(f"Cannot read {path}, skipped", file=sys.stderr)
        return False
    faces = detect_faces(img)
    if not faces:
        print(f"{path.name}: no face found, grade only", file=sys.stderr)
    warps = [FaceWarp(f, args.grin, args.eyes) for f in faces]
    for fw in warps:
        fw.apply(img)
    if not args.no_grade:
        img = horror_grade(img)
    if not args.no_hollow:
        for fw in warps:
            fw.hollow_eyes(img)
    if not cv2.imwrite(str(out_path), img):
        print(f"Cannot write {out_path}", file=sys.stderr)
        return False
    print(f"{path.name}: {len(faces)} face(s) -> {out_path}")
    return True


def collect(inputs):
    files = []
    for p in map(Path, inputs):
        if p.is_dir():
            files += sorted(q for q in p.iterdir()
                            if q.suffix.lower() in IMAGE_EXTS and not q.stem.endswith("_scary"))
        else:
            files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="Apply a scary smile filter to images.")
    ap.add_argument("inputs", nargs="+", help="image files or folders")
    ap.add_argument("-o", "--output", help="output file (single input only)")
    ap.add_argument("--grin", type=float, default=1.0, help="grin strength, 0 to 1.5 (default 1.0)")
    ap.add_argument("--eyes", type=float, default=0.3, help="eye enlargement, 0 to 0.6 (default 0.3)")
    ap.add_argument("--no-hollow", action="store_true", help="keep the natural eyes")
    ap.add_argument("--no-grade", action="store_true", help="skip the horror colour grade")
    args = ap.parse_args()
    args.eyes = min(max(args.eyes, 0.0), 0.6)
    args.grin = min(max(args.grin, 0.0), 1.5)

    if not MODEL.is_file():
        sys.exit(f"Face model missing: {MODEL}")
    files = collect(args.inputs)
    if args.output and len(files) != 1:
        sys.exit("-o needs exactly one input image")

    ok = True
    for f in files:
        out = Path(args.output) if args.output else f.with_name(f.stem + "_scary.png")
        ok = process(f, out, args) and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

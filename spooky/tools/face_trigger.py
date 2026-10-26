"""Camera-only test: watch for a face; when one holds steady, snap that frame and scare it.

The full show (python -m spooky) does this with LEDs, sounds and the display; this
is the quick check that the camera, detection and ScarySmile work on their own.

Usage (from the project root):
    python -m spooky.tools.face_trigger [--seconds 30] [--hold 3] [--show-fps]
"""

import argparse
import sys
import time

import cv2

from .. import config
from ..hw.camera import ROTATIONS, Camera, FaceDetector, quiet_opencv
from ..scare import scare


def main():
    cfg = config.load()
    ap = argparse.ArgumentParser(description="Face-triggered scary photo test.")
    ap.add_argument("--seconds", type=float, default=30, help="how long to watch (default 30)")
    ap.add_argument("--hold", type=int, default=3, help="consecutive frames with a face before snapping")
    ap.add_argument("--rotate", choices=ROTATIONS, default=cfg.camera.rotate, help="rotate camera frames")
    ap.add_argument("--show-fps", action="store_true", help="print detection rate every few seconds")
    args = ap.parse_args()

    quiet_opencv()
    captures = cfg.path(cfg.captures)
    captures.mkdir(exist_ok=True)
    cam = Camera(cfg.camera.index, (cfg.camera.width, cfg.camera.height), args.rotate)
    det = FaceDetector(cfg.camera.detect_scale, cfg.camera.min_score)

    streak, frames, t_rate = 0, 0, time.perf_counter()
    end = time.perf_counter() + args.seconds
    print(f"Watching for {args.seconds:.0f} s...")
    while time.perf_counter() < end:
        frame = cam.read()
        if frame is None:
            print("Camera read failed", file=sys.stderr)
            break
        streak = streak + 1 if len(det.detect(frame)) else 0
        frames += 1

        if args.show_fps and time.perf_counter() - t_rate > 5:
            print(f"  {frames / (time.perf_counter() - t_rate):.1f} fps")
            frames, t_rate = 0, time.perf_counter()

        if streak >= args.hold:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            t0 = time.perf_counter()
            scary, n = scare(frame, cfg.show.grin, cfg.show.eyes)
            cv2.imwrite(str(captures / f"{stamp}.jpg"), frame)
            cv2.imwrite(str(captures / f"{stamp}_scary.jpg"), scary)
            print(f"Face! {n} face(s) scared in {time.perf_counter() - t0:.2f} s -> captures/{stamp}_scary.jpg")
            streak = 0
            time.sleep(2)  # cooldown so one visitor isn't snapped repeatedly
            cam.flush()
            frames, t_rate = 0, time.perf_counter()

    cam.close()


if __name__ == "__main__":
    main()

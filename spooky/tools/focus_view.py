"""Live camera view in a browser with a sharpness meter, for focusing the lens by hand.

Open http://spooky-pi.local:8000 and twist the lens until the score peaks. The score
is measured on the detected face if there is one, otherwise on the centre of the frame.

Usage (from the project root):
    python -m spooky.tools.focus_view [--port 8000] [--rotate ccw]
"""

import argparse
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from .. import config
from ..hw.camera import ROTATIONS, Camera, FaceDetector, quiet_opencv

PAGE = b"""<!doctype html><title>spooky-pi focus</title>
<body style="margin:0;background:#111;display:flex;justify-content:center">
<img src="/stream" style="max-height:100vh;max-width:100vw"></body>"""

latest = None
cond = threading.Condition()


def camera_loop(cfg, rotate):
    global latest
    cam = Camera(cfg.camera.index, (cfg.camera.width, cfg.camera.height), rotate)
    det = FaceDetector(cfg.camera.detect_scale, cfg.camera.min_score)
    best = 0.0
    while True:
        frame = cam.read()
        if frame is None:
            continue
        h, w = frame.shape[:2]
        faces = det.detect(frame)
        if len(faces):
            x, y, bw, bh = faces[0][:4].astype(int)
            label = "face"
        else:
            bw, bh = w // 3, h // 3
            x, y = (w - bw) // 2, (h - bh) // 2
            label = "centre"
        x, y = max(x, 0), max(y, 0)
        roi = cv2.cvtColor(frame[y:y + bh, x:x + bw], cv2.COLOR_BGR2GRAY)
        score = cv2.Laplacian(roi, cv2.CV_64F).var() if roi.size else 0.0
        best = max(best * 0.995, score)  # slowly decaying peak so you can see when you passed it

        view = cv2.resize(frame, (w // 2, h // 2))
        s = 0.5
        cv2.rectangle(view, (int(x * s), int(y * s)), (int((x + bw) * s), int((y + bh) * s)), (0, 255, 0), 2)
        bar = int(min(score / max(best, 1e-6), 1.0) * (view.shape[1] - 20))
        cv2.rectangle(view, (10, 10), (10 + bar, 40), (0, 200, 255), -1)
        cv2.putText(view, f"{label} sharpness {score:6.1f}  peak {best:6.1f}", (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        _, jpg = cv2.imencode(".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, 80])
        with cond:
            latest = jpg.tobytes()
            cond.notify_all()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PAGE)
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            while True:
                with cond:
                    cond.wait()
                    jpg = latest
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


def main():
    cfg = config.load()
    ap = argparse.ArgumentParser(description="Browser focus helper.")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--rotate", choices=ROTATIONS, default=cfg.camera.rotate)
    args = ap.parse_args()
    quiet_opencv()
    threading.Thread(target=camera_loop, args=(cfg, args.rotate), daemon=True).start()
    print(f"Focus view at http://spooky-pi.local:{args.port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

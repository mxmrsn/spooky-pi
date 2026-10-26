"""Photo display backends. All take BGR numpy images (OpenCV's format).

Besides still images, every backend can show the live camera feed (mirrored, with a
prompt banner and an optional big centre text such as a countdown digit): call feed()
as often as you like; the next show()/card()/idle() replaces it.

    stream  serves the visitor screen as a web page (http://<pi>:8090/, an MJPEG stream
            underneath) for the Pi's own HDMI kiosk and any browser; writes the file too
    pygame  fullscreen on the Pi's own desktop (HDMI), without the web page
    file    writes what would be shown to a JPEG (simulation / headless)
    none    discards everything
"""

import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

ROTATE = {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def fit(img, size):
    """Letterbox a BGR image into size (w, h) on black."""
    w, h = size
    ih, iw = img.shape[:2]
    k = min(w / iw, h / ih)
    nw, nh = max(1, round(iw * k)), max(1, round(ih * k))
    out = np.zeros((h, w, 3), np.uint8)
    x, y = (w - nw) // 2, (h - nh) // 2
    out[y:y + nh, x:x + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    return out


def idle_card(size, text="Step closer... if you dare", max_chars=None):
    """Red text on black, wrapped to lines of ~max_chars and scaled to fill 85% of the width."""
    w, h = size
    max_chars = max_chars or (7 if h > w else 12)  # portrait screens: shorter, bigger lines
    out = np.zeros((h, w, 3), np.uint8)
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > max_chars:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    font = cv2.FONT_HERSHEY_DUPLEX
    widest = max(cv2.getTextSize(ln, font, 1.0, 2)[0][0] for ln in lines)
    scale = 0.85 * w / widest
    thick = max(2, round(2.5 * scale))
    line_h = cv2.getTextSize("Hg", font, scale, thick)[0][1] * 1.6
    y = (h - line_h * (len(lines) - 1)) / 2
    for ln in lines:
        (tw, th), _ = cv2.getTextSize(ln, font, scale, thick)
        cv2.putText(out, ln, ((w - tw) // 2, round(y + th / 2)), font, scale, (0, 0, 220), thick, cv2.LINE_AA)
        y += line_h
    return out


def _text(img, text, cx, cy, height, color=(0, 0, 220)):
    """Text centred on (cx, cy), about `height` px tall, with a black outline; at most 90% wide."""
    font = cv2.FONT_HERSHEY_DUPLEX
    (tw, th), _ = cv2.getTextSize(text, font, 1.0, 2)
    scale = min(height / th, 0.9 * img.shape[1] / tw)
    thick = max(2, round(2.2 * scale))
    (tw, th), _ = cv2.getTextSize(text, font, scale, thick)
    org = (round(cx - tw / 2), round(cy + th / 2))
    cv2.putText(img, text, org, font, scale, (0, 0, 0), thick * 3, cv2.LINE_AA)
    cv2.putText(img, text, org, font, scale, color, thick, cv2.LINE_AA)


def caption(img, prompt="", big=""):
    """Prompt banner near the bottom, and optional big text in the middle (drawn in place)."""
    h, w = img.shape[:2]
    if prompt:
        _text(img, prompt, w / 2, h * 0.88, h * 0.06)
    if big:
        _text(img, big, w / 2, h / 2, h * 0.3, (255, 255, 255))
    return img


def side_by_side(before, after, size, labels=("Before", "After")):
    """The two photos next to each other (stacked on a portrait screen), labelled."""
    w, h = size
    if w >= h:
        out = np.hstack([fit(before, (w // 2, h)), fit(after, (w - w // 2, h))])
        spots = [(w / 4, h * 0.06), (w * 3 / 4, h * 0.06)]
    else:
        out = np.vstack([fit(before, (w, h // 2)), fit(after, (w, h - h // 2))])
        spots = [(w / 2, h * 0.04), (w / 2, h / 2 + h * 0.04)]
    for label, (x, y) in zip(labels, spots):
        _text(out, label, x, y, h * 0.045, (255, 255, 255))
    return out


class _Base:
    LIVE_FPS = 15  # live feed frames per second, rendered from pump()

    def __init__(self, cfg, root):
        self.rotate = ROTATE[cfg.rotate % 360]
        p = root / cfg.idle_image
        self.idle_image = cv2.imread(str(p)) if p.is_file() else None
        self.watcher = None  # FaceWatcher for the live feed (set by hw.build)
        self.live = None  # (prompt, big) while the live feed is up
        self.stills = 0  # counts show() calls, so a live frame rendered meanwhile is dropped
        self._live_t = 0.0

    def _prep(self, img):
        return cv2.rotate(img, self.rotate) if self.rotate is not None else img

    def show(self, img):
        self.live = None
        self.stills += 1
        self._show(img)

    def _show_live(self, img):
        self._show(img)

    def feed(self, prompt="", big=""):
        """Show the live camera feed with a prompt. Cheap: call it every tick."""
        self.live = (prompt, big)

    def compose_live(self):
        prompt, big = self.live or ("", "")
        w, h = self.native_size()
        s = self.watcher.latest() if self.watcher is not None and self.watcher.enabled else None
        img = fit(cv2.flip(s.frame, 1), (w, h)) if s is not None else np.zeros((h, w, 3), np.uint8)
        return caption(img, prompt, big)

    def still(self, img, prompt=""):
        """A still photo with a prompt banner, e.g. while the scary version is made."""
        self.show(caption(fit(img, self.native_size()), prompt))

    def compare(self, before, after):
        self.show(side_by_side(before, after, self.native_size()))

    def flash(self):
        w, h = self.native_size()
        self.show(np.full((h, w, 3), 255, np.uint8))

    def idle(self):
        self.show(self.idle_image if self.idle_image is not None else idle_card(self.native_size()))

    def card(self, text):
        """Full-screen text, e.g. HOLD STILL! during the lock-on."""
        self.show(idle_card(self.native_size(), text))

    def pump(self):
        """Draw the live feed when due, handle window events; False if the user asked to quit."""
        now = time.monotonic()
        if self.live is not None and now - self._live_t >= 1 / self.LIVE_FPS:
            self._live_t = now
            self._show_live(self.compose_live())
        return True

    def close(self):
        pass


class PygameDisplay(_Base):
    def __init__(self, cfg, root):
        super().__init__(cfg, root)
        # When started over SSH, borrow the logged-in desktop session
        runtime = f"/run/user/{os.getuid()}"
        os.environ.setdefault("XDG_RUNTIME_DIR", runtime)
        if "WAYLAND_DISPLAY" not in os.environ and Path(runtime, "wayland-0").exists():
            os.environ["WAYLAND_DISPLAY"] = "wayland-0"
        import pygame
        pygame.display.init()
        self.pygame = pygame
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("spooky-pi")
        pygame.mouse.set_visible(False)
        log.info("display %dx%d", *self.screen.get_size())

    def native_size(self):
        w, h = self.screen.get_size()
        return (h, w) if self.rotate in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE) else (w, h)

    def _show(self, img):
        img = self._prep(fit(img, self.native_size()))
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        surf = self.pygame.image.frombuffer(rgb.tobytes(), (rgb.shape[1], rgb.shape[0]), "RGB")
        self.screen.blit(surf, (0, 0))
        self.pygame.display.flip()

    def pump(self):
        super().pump()
        for e in self.pygame.event.get():
            if e.type == self.pygame.QUIT or (e.type == self.pygame.KEYDOWN and e.key == self.pygame.K_ESCAPE):
                return False
        return True

    def close(self):
        self.pygame.display.quit()


class FileDisplay(_Base):
    """Writes each shown image to a JPEG (the Studio previews it from there)."""

    LIVE_FPS = 1  # spare the SD card

    def __init__(self, cfg, root):
        super().__init__(cfg, root)
        self.size = tuple(cfg.size)
        self.path = root / cfg.file_path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def native_size(self):
        w, h = self.size
        return (h, w) if self.rotate in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE) else (w, h)

    def render(self, img):
        """Letterboxed, rotated, display-sized JPEG bytes."""
        ok, jpg = cv2.imencode(".jpg", self._prep(fit(img, self.native_size())), [cv2.IMWRITE_JPEG_QUALITY, 88])
        return jpg.tobytes()

    def _show(self, img):
        self._write(self.render(img))

    def _show_live(self, img):
        self._write(self.render(img), quiet=True)

    def _write(self, jpg, quiet=False):
        tmp = self.path.with_suffix(".tmp.jpg")
        tmp.write_bytes(jpg)
        os.replace(tmp, self.path)
        if not quiet:
            log.info("display -> %s", self.path.name)


VIEWER = b"""<!doctype html><title>spooky display</title>
<style>html,body{margin:0;height:100%;background:#000;overflow:hidden;cursor:none}
img{width:100vw;height:100vh;object-fit:contain}</style>
<img id="s" src="/stream.mjpg">
<script>
// Kiosk-proof: if the show restarts, keep checking and reattach the stream once it's back.
const img = document.getElementById("s");
let down = false;
img.onerror = () => { down = true; };
setInterval(async () => {
  try {
    await fetch("/", {cache: "no-store"});
    if (down) { down = false; img.src = "/stream.mjpg?t=" + Date.now(); }
  } catch (e) { down = true; }
}, 2000);
</script>"""


CAMERA_VIEWER = b"""<!doctype html><title>spooky camera</title>
<style>html,body{margin:0;height:100%;background:#111;display:flex;align-items:center;justify-content:center}
img{max-width:100vw;max-height:100vh}</style>
<img src="/camera.mjpg" onerror="setTimeout(()=>location.reload(),2000)">"""


class StreamDisplay(FileDisplay):
    """The visitor screen over HTTP, for the Pi's HDMI kiosk (scripts/kiosk.sh) and any browser:

        /stream.mjpg   multipart JPEG stream: new image on every change, repeated every
                       KEEPALIVE s so a (re)connecting player gets a picture at once
        /frame.jpg     the current image
        /              full-screen viewer page for a browser kiosk
        /camera        live camera with the detected faces boxed, for setting up and
                       debugging (needs `watcher`, set by hw.build)
    """

    KEEPALIVE = 1.0
    CAMERA_FPS = 10
    LIVE_FPS = 10

    def __init__(self, cfg, root, host="0.0.0.0"):
        super().__init__(cfg, root)
        self.jpg = self.render(idle_card(self.native_size()))
        self.version = 0
        self.cond = threading.Condition()
        self.watcher = None  # FaceWatcher for the /camera preview
        display = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/stream.mjpg"):
                    return self._stream()
                if self.path.startswith("/camera.mjpg"):
                    return self._camera()
                body, ctype = {"/frame.jpg": (display.jpg, "image/jpeg"),
                               "/camera": (CAMERA_VIEWER, "text/html"),
                               "/": (VIEWER, "text/html")}.get(self.path, (None, None))
                if body is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _start_parts(self):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=spookyframe")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()

            def _part(self, jpg):
                head = b"--spookyframe\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg)
                self.wfile.write(head + jpg + b"\r\n")
                self.wfile.flush()

            def _camera(self):
                self._start_parts()
                try:
                    while not display.closed:
                        self._part(display.camera_jpg())
                        time.sleep(1 / display.CAMERA_FPS)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _stream(self):
                self._start_parts()
                log.info("display client connected: %s", self.client_address[0])
                seen = -1
                try:
                    while not display.closed:
                        with display.cond:
                            if display.version == seen:
                                display.cond.wait(display.KEEPALIVE)
                            jpg, seen = display.jpg, display.version
                        self._part(jpg)
                except (BrokenPipeError, ConnectionResetError):
                    log.info("display client left: %s", self.client_address[0])

            def log_message(self, fmt, *args):
                pass

        self.closed = False
        self.server = ThreadingHTTPServer((host, cfg.stream_port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self._live_loop, daemon=True).start()
        log.info("display stream on port %d", cfg.stream_port)

    def _live_loop(self):
        """Renders the live feed off the show's thread (a full-HD JPEG takes ~30 ms on a Pi 4)."""
        while not self.closed:
            stills = self.stills
            if self.live is not None:
                jpg = self.render(self.compose_live())
                with self.cond:
                    if self.stills == stills:  # a still image didn't replace the feed meanwhile
                        self.jpg, self.version = jpg, self.version + 1
                        self.cond.notify_all()
            time.sleep(1 / self.LIVE_FPS)

    def pump(self):
        return True  # live frames come from _live_loop

    def camera_jpg(self, width=640):
        """The camera's latest frame with its faces boxed, or a card while the camera is off."""
        w = self.watcher
        s = w.latest() if w is not None and w.enabled else None
        if s is None:
            img = np.full((width * 9 // 16, width, 3), 32, np.uint8)
            cv2.putText(img, "camera off" if w is not None else "no camera", (width // 2 - 90, width * 9 // 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (200, 200, 200), 2)
        else:
            k = width / s.frame.shape[1]
            img = cv2.resize(s.frame, (width, round(s.frame.shape[0] * k)))
            for f in s.faces:
                x, y, fw, fh = (np.array(f[:4]) * k).astype(int)
                cv2.rectangle(img, (x, y), (x + fw, y + fh), (40, 220, 40), 2)
                cv2.putText(img, f"{f[-1]:.2f}", (x, max(y - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 220, 40), 1)
            cv2.putText(img, f"{w.fps:.0f} fps, {len(s.faces)} face(s)", (8, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()

    def _show(self, img):
        jpg = self.render(img)
        with self.cond:
            self.jpg, self.version = jpg, self.version + 1
            self.cond.notify_all()
        self._write(jpg)

    def close(self):
        self.closed = True
        with self.cond:
            self.cond.notify_all()
        self.server.shutdown()
        self.server.server_close()


class NullDisplay(_Base):
    def __init__(self, cfg=None, root=None):
        self.rotate, self.idle_image, self.watcher, self.live, self.stills, self._live_t = None, None, None, None, 0, 0.0

    def native_size(self):
        return (1080, 1920)

    def _show(self, img):
        pass

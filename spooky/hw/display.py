"""Photo display backends. All take BGR numpy images (OpenCV's format).

    stream  serves an MJPEG stream for the i.MX 8M Plus display computer over Ethernet
            (http://<pi>:8090/stream.mjpg; see imx/README.md), and writes the file too
    pygame  fullscreen on the Pi's own desktop (HDMI)
    file    writes what would be shown to a JPEG (simulation / headless)
    none    discards everything
"""

import logging
import os
import threading
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


class _Base:
    def __init__(self, cfg, root):
        self.rotate = ROTATE[cfg.rotate % 360]
        p = root / cfg.idle_image
        self.idle_image = cv2.imread(str(p)) if p.is_file() else None

    def _prep(self, img):
        return cv2.rotate(img, self.rotate) if self.rotate is not None else img

    def idle(self):
        self.show(self.idle_image if self.idle_image is not None else idle_card(self.native_size()))

    def card(self, text):
        """Full-screen text, e.g. HOLD STILL! during the lock-on."""
        self.show(idle_card(self.native_size(), text))

    def pump(self):
        """Handle window events; returns False if the user asked to quit."""
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

    def show(self, img):
        img = self._prep(fit(img, self.native_size()))
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        surf = self.pygame.image.frombuffer(rgb.tobytes(), (rgb.shape[1], rgb.shape[0]), "RGB")
        self.screen.blit(surf, (0, 0))
        self.pygame.display.flip()

    def pump(self):
        for e in self.pygame.event.get():
            if e.type == self.pygame.QUIT or (e.type == self.pygame.KEYDOWN and e.key == self.pygame.K_ESCAPE):
                return False
        return True

    def close(self):
        self.pygame.display.quit()


class FileDisplay(_Base):
    """Writes each shown image to a JPEG (the Studio previews it from there)."""

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

    def show(self, img):
        self._write(self.render(img))

    def _write(self, jpg):
        tmp = self.path.with_suffix(".tmp.jpg")
        tmp.write_bytes(jpg)
        os.replace(tmp, self.path)
        log.info("display -> %s", self.path.name)


VIEWER = b"""<!doctype html><title>spooky display</title>
<style>html,body{margin:0;height:100%;background:#000;overflow:hidden}
img{width:100vw;height:100vh;object-fit:contain}</style>
<img src="/stream.mjpg" onerror="setTimeout(()=>location.reload(),2000)">"""


class StreamDisplay(FileDisplay):
    """MJPEG over HTTP for the display computer. It connects to the Pi and pulls:

        /stream.mjpg   multipart JPEG stream: new image on every change, repeated every
                       KEEPALIVE s so a (re)connecting player gets a picture at once
        /frame.jpg     the current image
        /              full-screen viewer page for a browser kiosk
    """

    KEEPALIVE = 1.0

    def __init__(self, cfg, root, host="0.0.0.0"):
        super().__init__(cfg, root)
        self.jpg = self.render(idle_card(self.native_size()))
        self.version = 0
        self.cond = threading.Condition()
        display = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/stream.mjpg"):
                    return self._stream()
                body, ctype = {"/frame.jpg": (display.jpg, "image/jpeg"),
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

            def _stream(self):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=spookyframe")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                log.info("display client connected: %s", self.client_address[0])
                seen = -1
                try:
                    while not display.closed:
                        with display.cond:
                            if display.version == seen:
                                display.cond.wait(display.KEEPALIVE)
                            jpg, seen = display.jpg, display.version
                        head = b"--spookyframe\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg)
                        self.wfile.write(head + jpg + b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    log.info("display client left: %s", self.client_address[0])

            def log_message(self, fmt, *args):
                pass

        self.closed = False
        self.server = ThreadingHTTPServer((host, cfg.stream_port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        log.info("display stream on port %d", cfg.stream_port)

    def show(self, img):
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
        self.rotate, self.idle_image = None, None

    def native_size(self):
        return (1080, 1920)

    def show(self, img):
        pass

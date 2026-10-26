"""The Pi's one web server, on [web] port (8090): the visitor screen, the camera view and
the control API that teammates use to drive the eyes, the show and the i.MX.

    GET  /                                visitor screen, full-screen (the HDMI kiosk shows this)
    GET  /stream.mjpg   /frame.jpg        the visitor screen as an MJPEG stream / its current picture
    GET  /camera                          the raw camera with detected faces boxed (setup, debugging)
    GET  /api                             this help
    GET  /api/eyes                        show state, eye state, any hold, every eye state
    POST /api/eyes  {"state": "rage"}                 hold an eye state until cleared
    POST /api/eyes  {"state": "rage", "seconds": 5}   ...or for a while
    POST /api/eyes  {"state": null}                   give the eyes back to the show
    POST /api/show  {"action": "wake"}                start a visit (from IDLE)
    POST /api/show  {"action": "reset"}               drop the visit and go back to IDLE
    POST /api/imx   {"animation": "reveal"}           tell the i.MX to play an animation now

Control commands are queued and applied on the show's next tick, so they're safe from
any thread. Guide: docs/EYES.md.
"""

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .. import scenes

log = logging.getLogger(__name__)
STATIC = Path(__file__).with_name("static")
ACTIONS = ("wake", "reset")


class WebServer:
    """`display` is a hw.display.WebDisplay (or None: no screen pages); `show` a Show (or None: no API)."""

    def __init__(self, port, display=None, show=None, host="0.0.0.0"):
        self.display, self.show, self.closed = display, show, False
        pages = {"/": STATIC / "viewer.html", "/camera": STATIC / "camera.html"}
        pages = {path: f.read_bytes() for path, f in pages.items()}
        web = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = urlparse(self.path).path
                if path in ("/api", "/api/"):
                    return self._send(200, __doc__.encode(), "text/plain; charset=utf-8")
                if path == "/api/eyes":
                    return self._api(lambda show: show.eyes_status())
                if web.display is None:
                    return self._json(404, {"error": "no visitor screen on this server"})
                if path == "/stream.mjpg":
                    return self._stream()
                if path == "/camera.mjpg":
                    return self._camera()
                if path == "/frame.jpg":
                    return self._send(200, web.display.jpg, "image/jpeg")
                if path in pages:
                    return self._send(200, pages[path], "text/html")
                self._json(404, {"error": f"no such page {path}"})

            def do_POST(self):
                path = urlparse(self.path).path
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                    if path == "/api/eyes":
                        state, seconds = body.get("state"), body.get("seconds")
                        if state is not None and state not in scenes.SCENES:
                            raise ValueError(f"unknown eye state {state!r}; choose from {', '.join(scenes.SCENES)}")
                        if seconds is not None and not (isinstance(seconds, (int, float)) and seconds > 0):
                            raise ValueError("seconds must be a positive number")
                        command = ("eyes", state, seconds)
                    elif path == "/api/show":
                        if body.get("action") not in ACTIONS:
                            raise ValueError(f"action must be one of {', '.join(ACTIONS)}")
                        command = (body["action"],)
                    elif path == "/api/imx":
                        animation = body.get("animation")
                        if not isinstance(animation, str) or not animation:
                            raise ValueError("animation must be a non-empty string")
                        if web.show is not None and web.show.dev.imx is None:
                            raise ValueError("i.MX triggers are off ([imx] host is empty)")
                        command = ("imx", animation)
                    else:
                        return self._json(404, {"error": f"no such endpoint {path}"})
                except (ValueError, AttributeError) as e:  # bad JSON, a non-object body, a bad value
                    return self._json(400, {"error": str(e)})
                if self._api(lambda show: show.command(*command) or {"ok": True}):
                    log.info("control: %s %s", path, body)

            def _api(self, call):
                if web.show is None:
                    self._json(503, {"error": "no show running"})
                    return False
                self._json(200, call(web.show))
                return True

            def _json(self, code, data):
                self._send(code, json.dumps(data).encode(), "application/json")

            def _send(self, code, body, ctype):
                self.send_response(code)
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

            def _stream(self):
                d = web.display
                self._start_parts()
                seen = -1
                try:
                    while not (web.closed or d.closed):
                        with d.cond:
                            if d.version == seen:
                                d.cond.wait(d.KEEPALIVE)
                            jpg, seen = d.jpg, d.version
                        self._part(jpg)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _camera(self):
                self._start_parts()
                try:
                    while not (web.closed or web.display.closed):
                        self._part(web.display.camera_jpg())
                        time.sleep(1 / web.display.CAMERA_FPS)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, fmt, *args):
                pass

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        log.info("web server on port %d: visitor screen /, camera /camera, control API /api", self.port)

    def close(self):
        self.closed = True
        self.server.shutdown()
        self.server.server_close()

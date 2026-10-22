"""Tiny JSON-over-HTTP layer for the Studio page (standard library only)."""

import json
import logging
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import StudioError

log = logging.getLogger(__name__)
STATIC = Path(__file__).with_name("static")


def make_server(studio, host="0.0.0.0", port=8080):
    get_routes = {
        "/api/info": lambda q: studio.info(),
        "/api/frame": lambda q: {"colors": studio.frame()},
        "/api/status": lambda q: studio.status(),
        "/api/library": lambda q: studio.library(),
        "/api/pir": lambda q: studio.pir_scope(),
    }
    post_routes = {
        "/api/preview": lambda b: studio.preview(b["name"]),
        "/api/preview_spec": lambda b: studio.preview_spec(b["spec"]),
        "/api/scene/save": lambda b: {"name": studio.save_scene(b["name"], b["spec"])},
        "/api/scene/delete": lambda b: studio.delete_scene(b["name"]),
        "/api/state_scene": lambda b: studio.set_state_scene(b["state"], b["scene"]),
        "/api/play": lambda b: studio.play(b["id"]),
        "/api/stop_sounds": lambda b: studio.stop_sounds(),
        "/api/clip/delete": lambda b: studio.delete_clip(b["id"]),
        "/api/voice": lambda b: {"name": studio.save_voice(b["name"], b.get("scene") or None,
                                                           b.get("talk", "pupils"), b.get("weight", 1.0))},
        "/api/show/start": lambda b: studio.start_show(b.get("camera", "sim")),
        "/api/show/stop": lambda b: studio.stop_show(),
        "/api/show/motion": lambda b: studio.motion(int(b.get("sensor", 0))),
        "/api/show/face": lambda b: {"face": studio.toggle_face()},
        "/api/pir/reset": lambda b: studio.pir_reset(),
    }

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # keep-alive; HTTP/1.0 close-after-each raced the page's first requests

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _call(self, fn, arg):
            try:
                result = fn(arg)
                self._send(200, result if result is not None else {"ok": True})
            except StudioError as e:
                self._send(400, {"error": str(e)})
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                self._send(400, {"error": f"Bad request: {e}"})
            except Exception as e:
                log.exception("studio request failed")
                self._send(500, {"error": f"Something went wrong: {e}"})

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in get_routes:
                return self._call(get_routes[url.path], parse_qs(url.query))
            if url.path == "/api/display.jpg":
                p = studio.display_path()
                return self._send(200, p.read_bytes(), "image/jpeg") if p.is_file() else self._send(404, {})
            name = "index.html" if url.path in ("/", "") else url.path.lstrip("/")
            p = (STATIC / name).resolve()
            if STATIC.resolve() in p.parents and p.is_file():
                return self._send(200, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "application/octet-stream")
            self._send(404, {"error": "not found"})

        def do_POST(self):
            url = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            if url.path == "/api/upload":
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                data = self.rfile.read(length)
                return self._call(lambda _: studio.upload(q.get("filename", "clip"), data, q.get("event", ""),
                                                          q.get("voice") or None, q.get("name") or None), None)
            if url.path not in post_routes:
                return self._send(404, {"error": "not found"})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as e:
                return self._send(400, {"error": f"Bad JSON: {e}"})
            self._call(post_routes[url.path], body)

        def log_message(self, fmt, *args):
            if not self.path.startswith(("/api/frame", "/api/status", "/api/pir")):
                log.debug(fmt, *args)

    return ThreadingHTTPServer((host, port), Handler)

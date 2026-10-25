"""Control API: lets teammates (or anything on the network) drive the eyes and the show.

    GET  /                                       this help
    GET  /eyes                                   show state, eye state, override, every eye state
    POST /eyes  {"state": "rage"}                hold an eye state until cleared
    POST /eyes  {"state": "rage", "seconds": 5}  ...or for a while
    POST /eyes  {"state": null}                  back to the show's own eye states
    POST /show  {"action": "wake"}               start a visit (as if a visitor walked up)
    POST /show  {"action": "reset"}              drop the visit and go back to IDLE

The show serves it on [control] port. Commands are queued and applied on the show's
next tick, so they're safe from any thread. Guide: docs/EYES.md.
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import scenes

log = logging.getLogger(__name__)
ACTIONS = ("wake", "reset")


class ControlServer:
    def __init__(self, show, port, host="0.0.0.0"):
        self.show = show

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in ("/", "/help"):
                    return self._send(200, __doc__, "text/plain; charset=utf-8")
                if self.path == "/eyes":
                    return self._json(200, show.eyes_status())
                self._json(404, {"error": f"no such endpoint {self.path}"})

            def do_POST(self):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                    if self.path == "/eyes":
                        state, seconds = body.get("state"), body.get("seconds")
                        if state is not None and state not in scenes.SCENES:
                            raise ValueError(f"unknown eye state {state!r}; choose from {', '.join(scenes.SCENES)}")
                        if seconds is not None and not (isinstance(seconds, (int, float)) and seconds > 0):
                            raise ValueError("seconds must be a positive number")
                        show.command("eyes", state, seconds)
                    elif self.path == "/show":
                        if body.get("action") not in ACTIONS:
                            raise ValueError(f"action must be one of {', '.join(ACTIONS)}")
                        show.command(body["action"])
                    else:
                        return self._json(404, {"error": f"no such endpoint {self.path}"})
                except (ValueError, AttributeError) as e:  # bad JSON, a non-object body, a bad value
                    return self._json(400, {"error": str(e)})
                log.info("control: %s %s", self.path, body)
                self._json(200, {"ok": True})

            def _json(self, code, data):
                self._send(code, json.dumps(data), "application/json")

            def _send(self, code, text, ctype):
                body = text.encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                pass

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        log.info("control API on port %d", self.port)

    def close(self):
        self.server.shutdown()
        self.server.server_close()

"""Live PIR scope in a browser: each sensor's level as a scrolling trace.

    python tools/pir_scope.py                            then open http://localhost:8091
    python tools/pir_scope.py --port /dev/cu.usbmodem*   Teensy on a Mac

Handy for wiring: watch the trace while you wave or probe. The Studio has the same scope
(Show → Motion sensors); this one needs nothing else running, but the Studio/show must be
stopped since they hold the Teensy.
"""

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from spooky import config  # noqa: E402
from spooky.hw import open_pirs  # noqa: E402
from spooky.hw.inputs import PirMonitor  # noqa: E402

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PIR scope</title>
<style>
:root{--bg:#fafaf7;--fg:#222;--muted:#777;--grid:#ddd;--hi:#d85a30;--lo:#1d9e75;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#1c1c1a;--fg:#eee;--muted:#999;--grid:#3a3a37;--hi:#f0997b;--lo:#5dcaa5;--card:#262624}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px system-ui,sans-serif}
h1{font-size:18px;font-weight:500;margin:0 0 4px}#link{color:var(--muted);font-size:13px}
#pills{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}
.pill{background:var(--card);border:1px solid var(--grid);border-radius:10px;padding:10px 14px;min-width:200px}
.lvl{font-size:26px;font-weight:600}.hi{color:var(--hi)}.lo{color:var(--lo)}.sub{color:var(--muted);font-size:13px}
canvas{width:100%;height:260px;background:var(--card);border:1px solid var(--grid);border-radius:10px}
</style></head><body>
<h1>PIR scope</h1><div id="link">connecting…</div>
<div id="pills"></div><canvas id="c"></canvas>
<script>
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
async function poll() {
  try {
    const d = await (await fetch("/api/pir")).json();
    document.getElementById("link").textContent = d.link;
    document.getElementById("pills").innerHTML = d.stats.map((st, i) => {
      const on = d.levels[i];
      return `<div class="pill"><div class="sub">PIR ${i + 1} · ${d.where}${d.pins[i]}</div>` +
        `<div class="lvl ${on ? "hi" : "lo"}">${on ? "HIGH · motion" : "low · quiet"}</div>` +
        `<div class="sub">${st.pulses} pulses · last high ${st.last_high == null ? "–" : st.last_high.toFixed(1) + " s"}` +
        ` · high ${st.high_pct}% of the time</div></div>`;
    }).join("");
    draw(d);
  } catch (e) {
    document.getElementById("link").textContent = "scope server not answering";
  }
  setTimeout(poll, 100);
}
function draw(d) {
  const c = document.getElementById("c"), dpr = devicePixelRatio || 1;
  c.width = c.clientWidth * dpr; c.height = c.clientHeight * dpr;
  const g = c.getContext("2d"); g.scale(dpr, dpr);
  const W = c.clientWidth, H = c.clientHeight, left = 70, lanes = d.pins.length, laneH = H / lanes;
  g.font = "12px system-ui"; g.fillStyle = css("--muted"); g.strokeStyle = css("--grid");
  for (let s = 0; s <= d.window; s += 5) {
    const x = left + (W - left - 10) * (1 - s / d.window);
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke();
    g.fillText(s ? `-${s}s` : "now", x - 14, H - 4);
  }
  d.pins.forEach((pin, i) => {
    const top = i * laneH, yHi = top + laneH * 0.2, yLo = top + laneH * 0.7;
    g.fillStyle = css("--fg"); g.fillText(`PIR ${i + 1}`, 10, top + laneH * 0.45);
    g.strokeStyle = d.levels[i] ? css("--hi") : css("--lo"); g.lineWidth = 2; g.beginPath();
    d.trace.forEach(([t, ...lv], k) => {
      const x = left + (W - left - 10) * (1 + t / d.window), y = lv[i] ? yHi : yLo;
      k ? g.lineTo(x, y) : g.moveTo(x, y);
    });
    g.stroke(); g.lineWidth = 1; g.strokeStyle = css("--grid");
  });
}
poll();
</script></body></html>"""


def main():
    cfg = config.load()
    ap = argparse.ArgumentParser(description="Live PIR scope in a browser.")
    ap.add_argument("--port", help="Teensy serial port (default: [teensy] port, else auto)")
    ap.add_argument("--http", type=int, default=8091, help="web port")
    args = ap.parse_args()
    if args.port:
        cfg.teensy.port = args.port

    pins, devices = open_pirs(cfg)
    mon = PirMonitor(pins, devices=devices)
    link = getattr(devices[0], "link", None)
    where = "Teensy pin " if cfg.teensy.enabled else "GPIO"

    def status():
        if link is None:
            return "Pi GPIO"
        if link.ser is None:
            return "Teensy link lost: reconnecting…"
        return f"Teensy: {link.hello or 'connected'}"

    def sampler():
        while True:
            mon.sample()
            time.sleep(0.02)

    threading.Thread(target=sampler, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api/pir"):
                body = json.dumps({**mon.snapshot(), "link": status(), "where": where}).encode()
                ctype = "application/json"
            else:
                body, ctype = PAGE.encode(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("", args.http), Handler)  # all interfaces: viewable from a PC when run on the Pi
    print(f"PIR scope: http://localhost:{args.http}  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        mon.close()


if __name__ == "__main__":
    main()

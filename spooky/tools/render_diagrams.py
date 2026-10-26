"""Render docs/diagrams/*.mmd (Mermaid source) to PNG + SVG in docs/img/ for the READMEs.

Uses headless Chrome/Edge and a pinned Mermaid from the jsDelivr CDN, so nothing
needs installing. Edit a .mmd file, then:

    python -m spooky.tools.render_diagrams            all diagrams
    python -m spooky.tools.render_diagrams states     just one
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC, OUT = ROOT / "docs" / "diagrams", ROOT / "docs" / "img"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.6.0/dist/mermaid.min.js"
SCALE = 2  # PNG pixel density
PAD = 16

CONFIG = {
    "startOnLoad": False,
    "theme": "base",
    "htmlLabels": True,  # label boxes get a solid background (PNG is what the READMEs use)
    "flowchart": {"htmlLabels": True, "curve": "stepAfter", "padding": 12},  # right-angled connectors
    "sequence": {"mirrorActors": False, "actorMargin": 40},
    "themeVariables": {
        "fontFamily": "Segoe UI, Helvetica, Arial, sans-serif",
        "fontSize": "15px",
        "primaryColor": "#fdecea",       # node fill
        "primaryBorderColor": "#b3261e",
        "primaryTextColor": "#1d1b1b",
        "lineColor": "#5f5555",
        "secondaryColor": "#eef6ea",     # subgraphs
        "tertiaryColor": "#f6f3f3",
        "clusterBkg": "#f6f3f3",
        "clusterBorder": "#9b8f8f",
        "noteBkgColor": "#fff4d6",
        "noteBorderColor": "#c79a1e",
        "actorBkg": "#fdecea",
        "actorBorder": "#b3261e",
        "signalColor": "#3b3434",
        "labelBoxBkgColor": "#fdecea",
        "edgeLabelBackground": "#ffffff",
    },
}

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;background:#fff}} #d{{padding:{pad}px;display:inline-block}}</style>
<script src="{mermaid}"></script></head><body><div id="d"></div>
<script>
mermaid.initialize({config});
mermaid.render("g", {source}).then(({{svg}}) => {{
  const d = document.getElementById("d");
  d.innerHTML = svg;
  const s = d.querySelector("svg");
  // Grow the viewBox to the drawn content: some diagram types draw past it (sequence notes)
  // Sequence lifelines are drawn absurdly long: measure without them, then trim them to fit
  const lifelines = [...s.querySelectorAll("line[class*='actor-line']")];
  lifelines.forEach(l => l.style.display = "none");
  const vb = s.viewBox.baseVal, bb = s.getBBox(), m = 4;
  lifelines.forEach(l => {{ l.style.display = ""; l.setAttribute("y2", bb.y + bb.height); }});
  const x0 = Math.min(vb.x, bb.x - m), y0 = Math.min(vb.y, bb.y - m);
  const w = Math.max(vb.x + vb.width, bb.x + bb.width + m) - x0;
  const h = Math.max(vb.y + vb.height, bb.y + bb.height + m) - y0;
  s.setAttribute("viewBox", `${{x0}} ${{y0}} ${{w}} ${{h}}`);
  s.removeAttribute("style"); s.setAttribute("width", w); s.setAttribute("height", h);
  document.body.setAttribute("data-size", Math.ceil(w) + "x" + Math.ceil(h));
}}).catch(e => document.body.setAttribute("data-error", String(e)));
</script></body></html>"""


def find_browser():
    candidates = [os.environ.get("CHROME"), shutil.which("chrome"), shutil.which("google-chrome"),
                  shutil.which("chromium"), shutil.which("chromium-browser"),
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    for c in candidates:
        if c and Path(c).exists():
            return c
    sys.exit("Chrome/Chromium/Edge not found; set CHROME=/path/to/browser")


def chrome(browser, *args):
    with tempfile.TemporaryDirectory() as profile:
        return subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                               f"--user-data-dir={profile}", "--virtual-time-budget=15000", *args],
                              capture_output=True, text=True, encoding="utf-8", timeout=120)


def render(browser, mmd, tmp):
    source = mmd.read_text(encoding="utf-8")

    def page():
        p = tmp / f"{mmd.stem}.html"
        p.write_text(PAGE.format(pad=PAD, mermaid=MERMAID, config=json.dumps(CONFIG),
                                 source=json.dumps(source)), encoding="utf-8")
        return p.as_uri()

    dom = chrome(browser, "--dump-dom", page()).stdout
    err = re.search(r'data-error="([^"]*)"', dom)
    if err:
        raise RuntimeError(err.group(1))
    size = re.search(r'data-size="(\d+)x(\d+)"', dom)
    svg = re.search(r"(<svg.*</svg>)", dom, re.S)
    if not size or not svg:
        raise RuntimeError("Mermaid did not render (offline? CDN blocked?)")
    w, h = int(size.group(1)) + 2 * PAD, int(size.group(2)) + 2 * PAD
    (OUT / f"{mmd.stem}.svg").write_text(svg.group(1), encoding="utf-8")
    png = OUT / f"{mmd.stem}.png"
    # Headless viewports come out a little smaller than --window-size, so shoot big and trim
    chrome(browser, f"--screenshot={png}", f"--window-size={w + 200},{h + 300}",
           f"--force-device-scale-factor={SCALE}", page())
    if not png.exists():
        raise RuntimeError("screenshot failed")
    return trim(png)


def trim(png):
    """Crop to the drawing plus PAD on white."""
    img = cv2.imread(str(png))
    ink = np.argwhere((img < 245).any(axis=2))
    (y0, x0), (y1, x1) = ink.min(0), ink.max(0)
    p = PAD * SCALE
    out = np.full((y1 - y0 + 1 + 2 * p, x1 - x0 + 1 + 2 * p, 3), 255, np.uint8)
    out[p:-p, p:-p] = img[y0:y1 + 1, x0:x1 + 1]
    cv2.imwrite(str(png), out)
    return out.shape[1] // SCALE, out.shape[0] // SCALE


def main():
    ap = argparse.ArgumentParser(description="Render Mermaid diagrams to PNG/SVG.")
    ap.add_argument("names", nargs="*", help="diagram names (default: all)")
    args = ap.parse_args()
    browser = find_browser()
    OUT.mkdir(parents=True, exist_ok=True)
    files = [SRC / f"{n}.mmd" for n in args.names] if args.names else sorted(SRC.glob("*.mmd"))
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for mmd in files:
            try:
                w, h = render(browser, mmd, Path(tmp))
                print(f"{mmd.stem:<12} {w}x{h} -> docs/img/{mmd.stem}.png")
            except Exception as e:
                failed += 1
                print(f"{mmd.stem:<12} FAILED: {e}", file=sys.stderr)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

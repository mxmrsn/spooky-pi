"""Drive the eyes and the show from a terminal, through the show's control API (docs/EYES.md).
Installed as `spooky-eyes`; from a clone without installing, use python -m spooky.tools.eyes.

    python -m spooky.tools.eyes                     what the show is doing, and every eye state
    python -m spooky.tools.eyes rage                hold "rage" until cleared
    python -m spooky.tools.eyes rage --seconds 5    ...or for 5 s
    python -m spooky.tools.eyes auto                back to the show's own eye states
    python -m spooky.tools.eyes --wake              start a visit
    python -m spooky.tools.eyes --reset             drop the visit, back to IDLE
    python -m spooky.tools.eyes --imx reveal        tell the i.MX to play its "reveal" animation
    python -m spooky.tools.eyes --hand strobe --color "#00ff00" --seconds 3
                                                    hold a handpiece look (--hand auto gives it back)

--host defaults to spooky-pi.local:8090 (or $SPOOKY_CONTROL). Standard library only.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def call(base, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(json.load(e).get("error", str(e)))
    except OSError as e:
        sys.exit(f"Can't reach the show at {base} ({e}). Is it running (spooky-mode.sh show)?")


def main():
    ap = argparse.ArgumentParser(description="Drive the eyes through the show's control API.")
    ap.add_argument("state", nargs="?", help='eye state to hold, or "auto" to give the eyes back to the show')
    ap.add_argument("--seconds", type=float, help="hold it this long (default: until cleared)")
    ap.add_argument("--wake", action="store_true", help="start a visit")
    ap.add_argument("--reset", action="store_true", help="drop the visit, back to IDLE")
    ap.add_argument("--imx", metavar="ANIMATION", help="tell the i.MX to play this animation")
    ap.add_argument("--hand", metavar="LOOK", help='hold a handpiece look ("auto" gives it back to the show)')
    ap.add_argument("--color", help="colour for --hand: #rrggbb or a palette name (blood, toxic, …)")
    ap.add_argument("--host", default=os.environ.get("SPOOKY_CONTROL", "spooky-pi.local:8090"))
    args = ap.parse_args()
    base = "http://" + args.host

    if args.wake or args.reset:
        call(base, "/api/show", {"action": "wake" if args.wake else "reset"})
    if args.imx:
        call(base, "/api/imx", {"animation": args.imx})
    if args.hand:
        look = None if args.hand == "auto" else args.hand
        call(base, "/api/handpiece", {"look": look, "color": args.color, "seconds": args.seconds})
    if args.state:
        call(base, "/api/eyes", {"state": None if args.state == "auto" else args.state, "seconds": args.seconds})
    acted = args.state or args.wake or args.reset or args.imx or args.hand
    if acted:
        time.sleep(0.1)  # commands apply on the show's next tick
    s = call(base, "/api/eyes")
    held = s["override"]
    left = f" for {held['seconds_left']} s more" if held and held["seconds_left"] is not None else ""
    print(f"show: {s['show_state']}   eyes: {s['eyes']}" + (f" (held{left})" if held else " (the show's)"))
    if s.get("handpiece"):
        h = s["handpiece"]
        hleft = f" for {h['seconds_left']} s more" if h["seconds_left"] is not None else ""
        print(f"handpiece: {h['look']}" + (f" (held{hleft})" if h["held"] else " (the show's)"))
    if not acted:
        print("eye states:", ", ".join(s["eye_states"]))
        print("show uses: " + ", ".join(f"{k}={v}" for k, v in s["show_eye_states"].items()))
        if s.get("handpiece_looks"):
            print("handpiece looks:", ", ".join(s["handpiece_looks"]))


if __name__ == "__main__":
    main()

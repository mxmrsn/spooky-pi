"""Drive the eyes and the show from a terminal, through the show's control API (docs/EYES.md).

    python tools/eyes.py                     what the show is doing, and every eye state
    python tools/eyes.py rage                hold "rage" until cleared
    python tools/eyes.py rage --seconds 5    ...or for 5 s
    python tools/eyes.py auto                back to the show's own eye states
    python tools/eyes.py --wake              start a visit
    python tools/eyes.py --reset             drop the visit, back to IDLE

--host defaults to spooky-pi.local:8070 (or $SPOOKY_CONTROL). Standard library only.
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
    ap.add_argument("--host", default=os.environ.get("SPOOKY_CONTROL", "spooky-pi.local:8070"))
    args = ap.parse_args()
    base = "http://" + args.host

    if args.wake or args.reset:
        call(base, "/show", {"action": "wake" if args.wake else "reset"})
    if args.state:
        call(base, "/eyes", {"state": None if args.state == "auto" else args.state, "seconds": args.seconds})
    if args.state or args.wake or args.reset:
        time.sleep(0.1)  # commands apply on the show's next tick
    s = call(base, "/eyes")
    held = s["override"]
    left = f" for {held['seconds_left']} s more" if held and held["seconds_left"] is not None else ""
    print(f"show: {s['show_state']}   eyes: {s['eyes']}" + (f" (held{left})" if held else " (the show's)"))
    if not (args.state or args.wake or args.reset):
        print("eye states:", ", ".join(s["eye_states"]))
        print("show uses: " + ", ".join(f"{k}={v}" for k, v in s["show_eye_states"].items()))


if __name__ == "__main__":
    main()

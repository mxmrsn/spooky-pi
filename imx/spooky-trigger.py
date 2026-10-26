#!/usr/bin/env python3
"""Reference receiver for the Pi's animation triggers, for the i.MX 8M Plus (see README.md).

    python3 spooky-trigger.py                              print each trigger
    python3 spooky-trigger.py --run "gst-play-1.0 --no-interactive /opt/spooky/{animation}.mp4"

Listens for UDP datagrams like {"cmd": "play", "animation": "reveal", "state": "REVEAL",
"seq": 12}. With --run it starts that command for each trigger, with {animation} filled in,
after stopping the previous one. Standard library only; also handy on a laptop for testing.
"""

import argparse
import json
import shlex
import socket
import subprocess


def main():
    ap = argparse.ArgumentParser(description="Play an animation for each trigger from the spooky-pi show.")
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--run", help='command per trigger; {animation} is replaced, e.g. "player /anim/{animation}.mp4"')
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))
    print(f"waiting for triggers on UDP {args.port}", flush=True)
    player = None
    while True:
        data, (sender, _) = sock.recvfrom(4096)
        try:
            msg = json.loads(data)
            animation = str(msg["animation"])
        except (ValueError, KeyError, TypeError):
            print(f"ignored from {sender}: {data[:80]!r}", flush=True)
            continue
        print(f"{sender}: play {animation} (state {msg.get('state')}, #{msg.get('seq')})", flush=True)
        if args.run:
            if player is not None and player.poll() is None:
                player.terminate()
            player = subprocess.Popen(shlex.split(args.run.format(animation=animation)))


if __name__ == "__main__":
    main()

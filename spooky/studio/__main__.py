"""Spooky Studio: a web page for playing with the glasses, sounds and show.

    python -m spooky.studio            then open http://spooky-pi.local:8080
    python -m spooky.studio --sim      no LEDs/speaker (e.g. on a laptop)

Don't run it at the same time as the show (python -m spooky): both want the LEDs.
"""

import argparse
import logging
import signal
import socket
import threading

from .. import config
from ..hw import open_strip
from ..hw.camera import quiet_opencv
from ..hw.leds import NullStrip
from ..hw.outputs import LogPlayer, PygamePlayer
from ..layout import Layout
from .core import RecordingLeds, Studio
from .server import make_server


def _stop(signum, frame):
    raise KeyboardInterrupt  # SDL (pygame) swallows SIGTERM otherwise; stop cleanly like Ctrl+C


def main():
    ap = argparse.ArgumentParser(prog="spooky.studio", description="Web studio for the glasses, sounds and show.")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--sim", action="store_true", help="don't drive the LEDs or play audio")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    log = logging.getLogger("spooky.studio")
    quiet_opencv()
    cfg = config.load()
    layout = Layout(cfg.leds)

    strip = NullStrip()
    if not args.sim:
        try:
            strip = open_strip(cfg)
        except Exception as e:
            log.warning("LEDs unavailable (%s): on-screen glasses only", e)
    player = LogPlayer()
    if not args.sim:
        try:
            player = PygamePlayer(cfg.audio.volume)
        except Exception as e:
            log.warning("audio unavailable (%s): sounds are silent", e)

    signal.signal(signal.SIGTERM, _stop)  # after pygame init, which installs its own
    leds = RecordingLeds(layout, strip)
    studio = Studio(cfg, leds, player)
    threading.Thread(target=studio.run, daemon=True).start()
    server = make_server(studio, port=args.port)
    log.info("Spooky Studio ready: http://%s.local:%d  (Ctrl+C to stop)", socket.gethostname(), args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        studio.stop()
        leds.close()
        server.server_close()


if __name__ == "__main__":
    main()

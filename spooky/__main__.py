"""Run the show.

    python -m spooky                 everything real (falls back per device if missing)
    python -m spooky --sim all       fully simulated: terminal LEDs, keyboard, photos as the camera
    python -m spooky --sim leds,audio  simulate just some devices
"""

import argparse
import logging
import signal

from . import config, hw
from .hw.display import WebDisplay
from .show import Show
from .web import WebServer


def _stop(signum, frame):
    raise KeyboardInterrupt  # systemd stop -> same clean shutdown as Ctrl+C


def main():
    ap = argparse.ArgumentParser(prog="spooky", description="Evil doctor Halloween show.")
    ap.add_argument("--sim", default="", help=f"devices to simulate: all or a comma list of {', '.join(hw.DEVICES)}")
    ap.add_argument("--config", help="settings file (default spooky.toml)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    cfg = config.load(args.config)
    dev = hw.build(cfg, [s for s in args.sim.split(",") if s])
    signal.signal(signal.SIGTERM, _stop)
    show = Show(cfg, dev)
    web = WebServer(cfg.web.port, display=dev.display if isinstance(dev.display, WebDisplay) else None, show=show)
    try:
        show.run()
    except KeyboardInterrupt:
        pass
    finally:
        web.close()
        dev.close()


if __name__ == "__main__":
    main()

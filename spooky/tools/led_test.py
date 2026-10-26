"""LED bring-up without the show: lights the raw chain, LED 0 first.

    python -m spooky.tools.led_test                  the whole configured chain
    python -m spooky.tools.led_test --count 16       just one ring
    python -m spooky.tools.led_test --brightness 0.3
    python -m spooky.tools.led_test --port /dev/cu.usbmodem*   Teensy on a Mac

Shows red, green and blue fills (checks the colour order), then a white dot chasing
along the chain with a dim trail, until Ctrl+C. Stop the Studio/show first: they
hold the LEDs (bash ~/spooky/scripts/pi/spooky-mode.sh off).
"""

import argparse
import time

import numpy as np

from .. import config
from ..hw import open_strip
from ..layout import Layout


def main():
    cfg = config.load()
    ap = argparse.ArgumentParser(description="Light the LED chain directly.")
    ap.add_argument("--count", type=int, default=Layout(cfg.leds).n_physical, help="LEDs on the chain")
    ap.add_argument("--brightness", type=float, default=0.15, help="0..1")
    ap.add_argument("--seconds", type=float, default=0, help="stop after this long (0 = until Ctrl+C)")
    ap.add_argument("--port", help="Teensy serial port (default: [teensy] port, else auto)")
    args = ap.parse_args()
    if args.port:
        cfg.teensy.port = args.port

    strip = open_strip(cfg)
    time.sleep(0.3)  # let the Teensy answer its hello
    hello = getattr(getattr(strip, "link", None), "hello", None)
    print(f"{type(strip).__name__}: {hello or 'connected'}; {args.count} LEDs", flush=True)
    level = int(255 * max(0.0, min(args.brightness, 1.0)))
    frame = np.zeros((args.count, 3), np.uint8)
    t0 = time.monotonic()
    try:
        while not args.seconds or time.monotonic() - t0 < args.seconds:
            for name, rgb in (("red", (level, 0, 0)), ("green", (0, level, 0)), ("blue", (0, 0, level))):
                print(f"  all {name}", flush=True)
                frame[:] = rgb
                strip.write(frame)
                time.sleep(1.0)
            print("  white dot chasing from LED 0", flush=True)
            for step in range(2 * args.count):
                frame[:] = 0
                for k, fade in enumerate((1.0, 0.3, 0.1)):
                    frame[(step - k) % args.count] = int(level * fade)
                strip.write(frame)
                time.sleep(0.06)
    except KeyboardInterrupt:
        pass
    finally:
        strip.write(np.zeros((args.count, 3), np.uint8))
        time.sleep(0.05)
        strip.close()


if __name__ == "__main__":
    main()

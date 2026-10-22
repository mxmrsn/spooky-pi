"""Preview LED scenes on the real glasses or in the terminal.

    python -m spooky.demo                  cycle through every scene, 5 s each
    python -m spooky.demo storm madness    just these, in turn
    python -m spooky.demo idle --sim       terminal preview instead of the LEDs
"""

import argparse
import itertools
import math
import time

from . import config, scenes
from .hw.leds import Leds, SpiStrip, TerminalStrip
from .layout import Layout


def main():
    ap = argparse.ArgumentParser(prog="spooky.demo", description="Preview LED scenes.")
    ap.add_argument("scenes", nargs="*", help=f"scene names (default: all): {', '.join(scenes.SCENES)}")
    ap.add_argument("--seconds", type=float, default=5.0, help="time per scene when cycling")
    ap.add_argument("--sim", action="store_true", help="draw in the terminal instead of driving the LEDs")
    ap.add_argument("--brightness", type=float, help="override the brightness cap")
    args = ap.parse_args()

    cfg = config.load()
    if args.brightness is not None:
        cfg.leds.brightness = args.brightness
    layout = Layout(cfg.leds)
    names = args.scenes or list(scenes.SCENES)
    strip = TerminalStrip(layout) if args.sim else SpiStrip(cfg.leds.spi_bus, cfg.leds.spi_device)
    leds = Leds(layout, strip)
    period = 1 / cfg.leds.fps
    try:
        for name in itertools.cycle(names) if len(names) > 1 else names:
            scene = scenes.make(name)
            t0 = time.monotonic()
            peak = 0.0
            while len(names) == 1 or time.monotonic() - t0 < args.seconds:
                t = time.monotonic() - t0
                if scene.gaze is not None:  # demo: look around in a slow circle
                    scene.gaze.look = (0.9 * math.sin(t), 0.9 * math.cos(t * 0.7))
                leds.show(scene.render(t, layout))
                peak = max(peak, layout.estimate_current_a(leds.last))
                leds.set_status(f"{name:<14} t={t:4.1f}s  est. LED current {layout.estimate_current_a(leds.last):.2f} A "
                                f"(peak {peak:.2f} A)")
                time.sleep(period)
    except KeyboardInterrupt:
        pass
    finally:
        leds.close()


if __name__ == "__main__":
    main()

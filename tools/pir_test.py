"""Live PIR check: prints every rising/falling edge with timestamps and how long the output stayed high.

    python tools/pir_test.py                 both sensors (config pins), 60 s
    python tools/pir_test.py --seconds 120   longer
    python tools/pir_test.py --pins 23       just one Pi GPIO pin (old driver board)
    python tools/pir_test.py --port /dev/cu.usbmodem*   Teensy on a Mac

With [teensy] enabled (the default) it reads the PIRs through the Teensy.

What good looks like: after a 30-60 s warm-up the output sits LOW while nothing moves,
goes HIGH when you wave, and drops back after the module's hold time (the "time" pot).
Stuck HIGH for minutes with nobody around usually means OUT and VCC are swapped.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from spooky import config  # noqa: E402
from spooky.hw import open_pirs  # noqa: E402


def main():
    cfg = config.load()
    ap = argparse.ArgumentParser(description="Live PIR edge logger.")
    ap.add_argument("--pins", type=int, nargs="+", help="Pi BCM pin numbers instead of the configured sensors")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--port", help="Teensy serial port (default: [teensy] port, else auto)")
    args = ap.parse_args()
    if args.port:
        cfg.teensy.port = args.port

    if args.pins:
        from gpiozero import DigitalInputDevice
        pins, devices, where = args.pins, [DigitalInputDevice(p, pull_up=False) for p in args.pins], "GPIO"
    else:
        (pins, devices), where = open_pirs(cfg), "Teensy pin " if cfg.teensy.enabled else "GPIO"
        time.sleep(0.6)  # the Teensy reports levels every 0.5 s
    t0 = time.monotonic()
    stamp = lambda: f"{time.monotonic() - t0:6.1f}s"  # noqa: E731
    sensors = {}
    for i, (pin, d) in enumerate(zip(pins, devices)):
        sensors[pin] = {"dev": d, "name": f"PIR {i + 1} ({where}{pin})", "since": time.monotonic(), "edges": 0,
                        "high_time": 0.0}
        print(f"{stamp()}  {sensors[pin]['name']} starts {'HIGH' if d.value else 'low'}", flush=True)

    def edge(pin, level):
        s = sensors[pin]
        now = time.monotonic()
        held = now - s["since"]
        if not level:
            s["high_time"] += held
        s["since"], s["edges"] = now, s["edges"] + 1
        what = "HIGH  <- motion" if level else f"low   (was high {held:.1f} s)"
        print(f"{stamp()}  {s['name']}: {what}", flush=True)

    for pin, s in sensors.items():
        s["dev"].when_activated = lambda pin=pin: edge(pin, True)
        s["dev"].when_deactivated = lambda pin=pin: edge(pin, False)

    print(f"Watching for {args.seconds:.0f} s. Stay still for a bit, then wave...", flush=True)
    try:
        time.sleep(args.seconds)
    except KeyboardInterrupt:
        pass
    print("--- summary")
    for s in sensors.values():
        if s["dev"].value:
            s["high_time"] += time.monotonic() - s["since"]
        print(f"{s['name']}: {s['edges']} edges, high {s['high_time']:.1f} s of {time.monotonic() - t0:.0f} s, "
              f"now {'HIGH' if s['dev'].value else 'low'}")
        s["dev"].close()


if __name__ == "__main__":
    main()

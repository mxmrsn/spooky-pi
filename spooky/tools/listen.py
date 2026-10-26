"""Hear the Pi's audio on this computer, e.g. while no speaker is plugged into the Pi.

    pip install sounddevice numpy
    python -m spooky.tools.listen                  until Ctrl+C
    python -m spooky.tools.listen --gain 2         louder (the Pi's own volume applies too)

Records what the Pi plays (a monitor of its default output) with PipeWire and streams
it over SSH as raw 16-bit PCM. Expect about a quarter of a second of delay.
"""

import argparse
import os
import subprocess
import sys

import numpy as np

RATE, CHANNELS = 48000, 2


def main():
    ap = argparse.ArgumentParser(description="Play the Pi's audio output here.")
    ap.add_argument("--host", default=os.environ.get("SPOOKY_HOST", "spooky-pi@spooky-pi.local"))
    ap.add_argument("--gain", type=float, default=1.0)
    args = ap.parse_args()

    import sounddevice as sd
    cmd = ["ssh", "-o", "BatchMode=yes", args.host,
           'exec pw-record --raw -P "{ stream.capture.sink=true }" '
           f"--format s16 --rate {RATE} --channels {CHANNELS} --latency 50ms -"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    block = RATE // 50 * CHANNELS * 2  # 20 ms
    print(f"Listening to {args.host} (Ctrl+C to stop)", flush=True)
    try:
        with sd.RawOutputStream(samplerate=RATE, channels=CHANNELS, dtype="int16", latency="low") as out:
            while True:
                data = proc.stdout.read(block)
                if not data:
                    sys.exit("The Pi stopped sending audio.")
                if args.gain != 1.0:
                    pcm = np.frombuffer(data, np.int16).astype(np.float32) * args.gain
                    data = np.clip(pcm, -32768, 32767).astype(np.int16).tobytes()
                out.write(data)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()

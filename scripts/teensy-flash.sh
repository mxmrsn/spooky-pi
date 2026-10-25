#!/usr/bin/env bash
# Build the Teensy firmware on this computer and flash it through the Pi, whose USB the
# Teensy hangs off. The show/Studio is stopped while flashing (it holds the serial port)
# and started again afterwards.
#
#   bash scripts/teensy-flash.sh          Teensy on the Pi (needs teensy-loader-cli there: pi-setup.sh step 4)
#   bash scripts/teensy-flash.sh --here   Teensy plugged into this computer instead
#
# Needs arduino-cli with the Teensy core here (https://www.pjrc.com/teensy/td_download.html).
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${SPOOKY_HOST:-spooky-pi@spooky-pi.local}"
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT

arduino-cli compile --fqbn teensy:avr:teensy41 --output-dir "$OUT" teensy/spooky_teensy | tail -4

if [ "${1:-}" = "--here" ]; then
  port=$(arduino-cli board list --format json | python3 -c '
import json, sys
for p in json.load(sys.stdin).get("detected_ports", []):
    if p["port"].get("protocol") == "teensy":
        print(p["port"]["address"]); break')
  [ -n "$port" ] || { echo "No Teensy on this computer's USB."; exit 1; }
  arduino-cli upload --fqbn teensy:avr:teensy41 -p "$port" --input-dir "$OUT" teensy/spooky_teensy
  exit
fi
scp -q "$OUT/spooky_teensy.ino.hex" "$HOST:/tmp/spooky_teensy.hex"

ssh "$HOST" 'bash -s' <<'EOF'
set -eu
SC="systemctl --user"
running=$($SC list-units --state=active --plain --no-legend 'spooky-*.service' | awk '{print $1}')
if [ -n "$running" ]; then $SC stop $running; fi
port=$(ls /dev/serial/by-id/*Teensyduino* 2>/dev/null | head -1 || true)
if [ -n "$port" ]; then  # opening the port at 134 baud reboots a Teensy into its bootloader
  python3 -c "import serial, sys; serial.Serial(sys.argv[1], 134).close()" "$port" 2>/dev/null || true
else
  echo "No Teensy serial port: press the button on the Teensy to start flashing."
fi
timeout 60 teensy_loader_cli --mcu=TEENSY41 -w -v /tmp/spooky_teensy.hex \
  || { echo "Flashing failed or timed out. Is the Teensy plugged into the Pi and powered?"; exit 1; }
for _ in $(seq 20); do  # wait for it to come back and say hello
  port=$(ls /dev/serial/by-id/*Teensyduino* 2>/dev/null | head -1 || true)
  [ -n "$port" ] && break
  sleep 0.5
done
python3 - "$port" <<'PY'
import serial, sys, time
s = serial.Serial(sys.argv[1], timeout=0.5)
s.write(b"?")
end = time.monotonic() + 2
while time.monotonic() < end:
    line = s.readline().decode(errors="replace").strip()
    if line.startswith("spooky-teensy"):
        print("Teensy says:", line)
        break
else:
    sys.exit("The Teensy didn't answer with the spooky firmware.")
PY
if [ -n "$running" ]; then $SC start $running; echo "Restarted $running"; fi
EOF

#!/usr/bin/env bash
# Run by the show/Studio services before they start (ExecStartPre): at power-up the
# Teensy and the camera can show up a few seconds after the Pi, and the show would
# otherwise start without them. Waits up to $1 seconds (default 45), then lets the
# show start anyway with whatever is there.
set -u
limit="${1:-45}"
for ((i = 0; i < limit; i++)); do
  teensy=$(ls /dev/serial/by-id/*Teensyduino* 2>/dev/null | head -1)
  if [ -n "$teensy" ] && [ -e /dev/video0 ]; then
    [ "$i" -gt 0 ] && echo "hardware ready after ${i} s"
    exit 0
  fi
  sleep 1
done
[ -z "$teensy" ] && echo "no Teensy after ${limit} s: starting without the LEDs"
[ -e /dev/video0 ] || echo "no camera after ${limit} s: starting without it"
exit 0

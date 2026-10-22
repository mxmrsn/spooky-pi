#!/usr/bin/env bash
# Double-click (Mac) or run (Linux) to stop Spooky Studio on the Pi (e.g. before running the real show).
PI_HOST=spooky-pi.local
PI_USER=spooky-pi

echo
echo "  Stopping Spooky Studio on the Pi..."
echo
if ! ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$PI_USER@$PI_HOST" \
     "bash ~/spooky/scripts/studio-ctl.sh stop"; then
  echo
  echo "  Couldn't reach the Pi. Check that it's switched on and on the same network."
  echo
  read -r -p "  Press Enter to close..."
fi

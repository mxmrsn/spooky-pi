#!/usr/bin/env bash
# Set up a freshly imaged Pi for the demo, from your PC (guide: docs/PI-SETUP.md).
#
#   bash scripts/pc/setup-new-pi.sh        SPOOKY_HOST=user@host to use another address
#
# Waits for the Pi, makes sure your SSH key works, copies the code over (deploy.sh), then
# runs scripts/pi/pi-setup.sh on the Pi, which asks for the Pi password once and reboots.
set -euo pipefail
cd "$(dirname "$0")/../.."
HOST="${SPOOKY_HOST:-spooky-pi@spooky-pi.local}"
NAME="${HOST#*@}"

echo "== Waiting for $NAME"
until ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new "$HOST" true 2>/tmp/spooky-ssh.err; do
  if grep -q "REMOTE HOST IDENTIFICATION HAS CHANGED\|Host key verification failed" /tmp/spooky-ssh.err; then
    echo "   $NAME has a new host key (expected after re-imaging); forgetting the old one"
    ssh-keygen -R "$NAME" >/dev/null 2>&1
  elif grep -q "Permission denied" /tmp/spooky-ssh.err; then
    echo "   Your SSH key isn't on the Pi yet; enter the Pi password to add it"
    ssh-copy-id -o StrictHostKeyChecking=accept-new "$HOST"
  else
    sleep 3
  fi
done
echo "   connected"

echo "== Copying the code"
bash scripts/pc/deploy.sh

echo "== Setting up the Pi (asks for the Pi password)"
ssh -t "$HOST" "sudo bash ~/spooky/scripts/pi/pi-setup.sh"

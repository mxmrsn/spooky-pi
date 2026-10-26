#!/usr/bin/env bash
# Copy the project to the Pi (~/spooky). Code changes take effect after
#   ssh spooky-pi@spooky-pi.local "bash ~/spooky/scripts/pi/spooky-mode.sh restart"
# A new Pi, or new dependencies in pyproject.toml: run scripts/pc/setup-new-pi.sh instead.
#
#   bash scripts/pc/deploy.sh          SPOOKY_HOST=user@host to use another address
set -euo pipefail
cd "$(dirname "$0")/../.."
HOST="${SPOOKY_HOST:-spooky-pi@spooky-pi.local}"

tar czf - --exclude=__pycache__ --exclude=.pytest_cache --exclude=*.egg-info \
    spooky tests scripts sounds media pyproject.toml README.md spooky.example.toml \
    $( [ -f spooky.toml ] && echo spooky.toml ) \
  | ssh "$HOST" "mkdir -p spooky && tar xzf - -C spooky"
echo "Deployed to $HOST:~/spooky"

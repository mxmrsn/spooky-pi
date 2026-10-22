#!/usr/bin/env bash
# Copy the project to the Pi (~/spooky) and install Python deps into its venv.
#   ./deploy.sh            copy code
#   ./deploy.sh --setup    also (re)create the venv and install requirements
set -euo pipefail

HOST="${SPOOKY_HOST:-spooky-pi@spooky-pi.local}"
DEST="spooky"
cd "$(dirname "$0")"

tar czf - --exclude=__pycache__ --exclude=.pytest_cache --exclude=captures --exclude=.venv \
    spooky tools tests ScarySmile sounds media requirements.txt pyproject.toml spooky.example.toml \
    $( [ -f spooky.toml ] && echo spooky.toml ) \
  | ssh "$HOST" "mkdir -p $DEST && tar xzf - -C $DEST"

if [ "${1:-}" = "--setup" ]; then
  ssh "$HOST" "cd $DEST && { [ -d .venv ] || python3 -m venv --system-site-packages .venv; } \
    && .venv/bin/pip install -q -r requirements.txt"
fi
echo "Deployed to $HOST:~/$DEST"

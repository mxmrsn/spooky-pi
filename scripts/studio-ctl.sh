#!/usr/bin/env bash
# Start, stop or check Spooky Studio on the Pi. The launchers in launchers/ call this over SSH.
#
#   bash ~/spooky/scripts/studio-ctl.sh start|stop|restart|status|log
set -u
cd "$(dirname "$0")/.."

PORT=8080
LOG="$HOME/studio.log"
URL="http://$(hostname).local:$PORT"
STUDIO="python -m spooky.studio"
SHOW="python -m spooky( |$)"  # the show itself, not spooky.studio / spooky.demo (pgrep patterns are regex)

running() { pgrep -f "$STUDIO" >/dev/null; }
answering() { curl -s -o /dev/null --max-time 2 "http://localhost:$PORT/api/status"; }

start() {
  if running; then
    echo "Spooky Studio is already running."
  else
    if pgrep -f "$SHOW" >/dev/null; then
      echo "The show is running and is using the lights and speaker."
      echo "Stop the show first, then try again."
      exit 2
    fi
    echo "Starting Spooky Studio..."
    # setsid + no stdin: keeps running after the SSH session that started it closes
    setsid nohup .venv/bin/python -m spooky.studio --port "$PORT" >"$LOG" 2>&1 </dev/null &
    for _ in $(seq 1 40); do
      answering && break
      sleep 0.5
    done
    if ! answering; then
      echo "Spooky Studio didn't start. Last lines of $LOG:"
      tail -n 15 "$LOG"
      exit 1
    fi
  fi
  echo "Ready: $URL"
}

stop() {
  if ! running; then
    echo "Spooky Studio isn't running."
    return
  fi
  pkill -f "$STUDIO"
  for _ in $(seq 1 20); do
    running || break
    sleep 0.5
  done
  if running; then
    pkill -9 -f "$STUDIO"
  fi
  echo "Spooky Studio stopped."
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status)
    if running && answering; then echo "Running: $URL"; elif running; then echo "Starting up..."; else echo "Not running."; fi ;;
  log) tail -n 40 "$LOG" ;;
  *) echo "usage: $0 start|stop|restart|status|log"; exit 64 ;;
esac

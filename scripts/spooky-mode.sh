#!/usr/bin/env bash
# Choose what the Pi runs, now and after every reboot. Only one can run at a time:
# both use the lights, speaker and display.
#
#   bash ~/spooky/scripts/spooky-mode.sh studio    artists' week: Spooky Studio on port 8080
#   bash ~/spooky/scripts/spooky-mode.sh show      event: the real show
#   bash ~/spooky/scripts/spooky-mode.sh off       neither
#   bash ~/spooky/scripts/spooky-mode.sh status    what's running / starts at boot
#   bash ~/spooky/scripts/spooky-mode.sh restart   restart whichever is running (after ./deploy.sh)
#   bash ~/spooky/scripts/spooky-mode.sh log [N]   last N log lines of whichever is running
#   bash ~/spooky/scripts/spooky-mode.sh install   (re)install the service files
set -u
cd "$(dirname "$0")/.."
UNITS=(spooky-studio spooky-show)
SC="systemctl --user"

install() {
  mkdir -p ~/.config/systemd/user
  cp scripts/systemd/spooky-studio.service scripts/systemd/spooky-show.service ~/.config/systemd/user/
  $SC daemon-reload
}

# Stop anything started by hand (python -m ... from a terminal or the old launcher)
stray() {
  pkill -f "python -m spooky.studio" 2>/dev/null
  pkill -f -x ".*python -m spooky( .*)?" 2>/dev/null
  sleep 1
}

switch() {  # switch <unit to run, or none>
  [ -f ~/.config/systemd/user/spooky-studio.service ] || install
  for u in "${UNITS[@]}"; do
    if [ "$u" != "$1" ]; then $SC disable --now "$u" 2>/dev/null; fi
  done
  stray
  if [ "$1" != none ]; then
    $SC enable --now "$1"
    sleep 3
    $SC is-active --quiet "$1" && echo "$1 is running and will start at boot." \
      || { echo "$1 didn't start:"; journalctl --user-unit "$1" -n 20 --no-pager; exit 1; }
  else
    echo "Nothing runs now or at boot."
  fi
}

case "${1:-status}" in
  studio) switch spooky-studio ;;
  show) switch spooky-show ;;
  off) switch none ;;
  install) install; echo "Service files installed." ;;
  log)
    for u in "${UNITS[@]}"; do
      if $SC is-active --quiet "$u"; then
        echo "== $u (last ${2:-40} lines)"
        journalctl --user-unit "$u" -n "${2:-40}" --no-pager -o cat | grep -vE "swigvarlink|^pygame |^Hello from"
      fi
    done ;;
  restart)
    for u in "${UNITS[@]}"; do
      if $SC is-active --quiet "$u"; then $SC restart "$u" && echo "Restarted $u"; fi
    done ;;
  status)
    for u in "${UNITS[@]}"; do
      printf "%-15s now: %-9s at boot: %s\n" "$u" "$($SC is-active "$u" 2>/dev/null)" "$($SC is-enabled "$u" 2>/dev/null)"
    done ;;
  *) echo "usage: $0 studio|show|off|status|restart|log|install"; exit 64 ;;
esac

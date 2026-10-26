#!/usr/bin/env bash
# Choose what the Pi runs, now and after every reboot. Only one can run at a time:
# both use the lights, speaker and display.
#
#   bash ~/spooky/scripts/pi/spooky-mode.sh studio    artists' week: Spooky Studio on port 8080
#   bash ~/spooky/scripts/pi/spooky-mode.sh show      event: the real show
#   bash ~/spooky/scripts/pi/spooky-mode.sh off       neither
#   bash ~/spooky/scripts/pi/spooky-mode.sh status    what's running / starts at boot
#   bash ~/spooky/scripts/pi/spooky-mode.sh restart   restart whichever is running (after scripts/pc/deploy.sh;
#                                                  also reinstalls the service files)
#   bash ~/spooky/scripts/pi/spooky-mode.sh log [N]   last N log lines of whichever is running
#   bash ~/spooky/scripts/pi/spooky-mode.sh install   (re)install the service files
#   bash ~/spooky/scripts/pi/spooky-mode.sh kiosk on|off   the visitor screen full-screen on the Pi's
#                                                  own HDMI, now and at every login
set -u
cd "$(dirname "$0")/../.."
UNITS=(spooky-studio spooky-show)
SC="systemctl --user"

install() {
  mkdir -p ~/.config/systemd/user
  cp scripts/pi/systemd/spooky-studio.service scripts/pi/systemd/spooky-show.service ~/.config/systemd/user/
  $SC daemon-reload
}

# Stop anything started by hand (python -m ... from a terminal or the old launcher)
stray() {
  pkill -f "python -m spooky.studio" 2>/dev/null
  pkill -f -x ".*python -m spooky( .*)?" 2>/dev/null
  sleep 1
}

switch() {  # switch <unit to run, or none>
  install  # pick up any changed service files
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
  studio)
    switch spooky-studio
    for _ in $(seq 40); do  # the launchers open the page as soon as this returns
      curl -s -o /dev/null --max-time 2 http://localhost:8080/api/status && break
      sleep 0.5
    done
    echo "Spooky Studio: http://$(hostname).local:8080" ;;
  show) switch spooky-show ;;
  off) switch none ;;
  install) install; echo "Service files installed." ;;
  kiosk)
    AUTOSTART=~/.config/autostart/spooky-kiosk.desktop
    case "${2:-}" in
      on)
        mkdir -p ~/.config/autostart
        sed "s|@HOME@|$HOME|" scripts/pi/spooky-kiosk.desktop > "$AUTOSTART"
        if ! pgrep -f scripts/pi/kiosk.sh >/dev/null; then
          WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) setsid -f bash scripts/pi/kiosk.sh >/dev/null 2>&1
        fi
        echo "Kiosk on: the visitor screen fills the Pi's HDMI, now and at every login." ;;
      off)
        rm -f "$AUTOSTART"
        pkill -f scripts/pi/kiosk.sh; pkill -f "chromium.*--kiosk"
        echo "Kiosk off." ;;
      *) echo "kiosk: $([ -f "$AUTOSTART" ] && echo on || echo off)   (usage: $0 kiosk on|off)" ;;
    esac ;;
  log)
    for u in "${UNITS[@]}"; do
      if $SC is-active --quiet "$u"; then
        echo "== $u (last ${2:-40} lines)"
        journalctl --user-unit "$u" -n "${2:-40}" --no-pager -o cat | grep -vE "swigvarlink|^pygame |^Hello from"
      fi
    done ;;
  restart)
    install
    for u in "${UNITS[@]}"; do
      if $SC is-active --quiet "$u"; then $SC restart "$u" && echo "Restarted $u"; fi
    done ;;
  status)
    for u in "${UNITS[@]}"; do
      printf "%-15s now: %-9s at boot: %s\n" "$u" "$($SC is-active "$u" 2>/dev/null)" "$($SC is-enabled "$u" 2>/dev/null)"
    done
    printf "%-15s %s\n" "HDMI kiosk" "$([ -f ~/.config/autostart/spooky-kiosk.desktop ] && echo on || echo off)" ;;
  *) echo "usage: $0 studio|show|off|status|restart|log|install|kiosk on|off"; exit 64 ;;
esac

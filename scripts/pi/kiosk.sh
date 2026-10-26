#!/usr/bin/env bash
# The visitor screen full-screen on the Pi's own HDMI: Chromium in kiosk mode on
# http://localhost:8090/ (the show's display page). Started at desktop login by
# ~/.config/autostart/spooky-kiosk.desktop; turn it on or off with
#   bash ~/spooky/scripts/pi/spooky-mode.sh kiosk on|off
URL="${1:-http://localhost:8090/}"
until curl -sf -o /dev/null --max-time 2 "$URL"; do sleep 2; done  # wait for the show
while true; do
  chromium --kiosk --noerrdialogs --disable-infobars --no-first-run --incognito \
    --disable-session-crashed-bubble --password-store=basic --ozone-platform=wayland \
    --check-for-update-interval=31536000 "$URL"
  sleep 3  # closed or crashed: open it again
done

#!/usr/bin/env bash
# Double-click (Mac) or run (Linux) to start Spooky Studio on the Pi and open it in your browser.
# If spooky-pi.local doesn't work on your network, put the Pi's address here instead (e.g. 10.0.3.68).
PI_HOST=spooky-pi.local
PI_USER=spooky-pi

echo
echo "  Starting Spooky Studio on the Pi..."
echo "  (If it asks for a password, type the Pi password and press Enter."
echo "   The letters won't show while you type - that's normal.)"
echo
if ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$PI_USER@$PI_HOST" \
     "bash ~/spooky/scripts/studio-ctl.sh start"; then
  URL="http://$PI_HOST:8080"
  echo
  if command -v open >/dev/null; then open "$URL"; echo "  Spooky Studio is open in your browser. You can close this window."
  elif command -v xdg-open >/dev/null; then xdg-open "$URL" >/dev/null 2>&1; echo "  Spooky Studio is open in your browser. You can close this window."
  else echo "  Open $URL in your browser."
  fi
else
  echo
  echo "  Couldn't start Spooky Studio. Check that the Pi is switched on and on the same network,"
  echo "  then try again. If it keeps failing, send a photo of this window to the project team."
  echo
  read -r -p "  Press Enter to close..."
fi

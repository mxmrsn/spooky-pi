#!/bin/sh
# Show the spooky-pi display stream full-screen on the i.MX 8M Plus (Yocto). Plain POSIX sh.
# Reconnects forever, so it can start before the Pi and survives Pi reboots.
#
# Settings (environment variables, all optional):
#   SPOOKY_PI     Pi address on the show network     (default 192.168.77.1)
#   SPOOKY_PORT   stream port                        (default 8090)
#   SPOOKY_SINK   GStreamer video sink to force, e.g. "waylandsink fullscreen=true" or "kmssink"

PI="${SPOOKY_PI:-192.168.77.1}"
PORT="${SPOOKY_PORT:-8090}"
URL="http://$PI:$PORT/stream.mjpg"

has() { gst-inspect-1.0 "$1" >/dev/null 2>&1; }

if ! command -v gst-launch-1.0 >/dev/null 2>&1; then
  echo "spooky-display: gst-launch-1.0 not found - this image needs GStreamer" >&2
  exit 1
fi

# Video sink: Weston (Wayland) desktop if there is one, else straight to the screen
if [ -n "$SPOOKY_SINK" ]; then
  SINK="$SPOOKY_SINK"
elif has waylandsink && [ -n "$WAYLAND_DISPLAY" ]; then
  SINK="waylandsink fullscreen=true"
elif has kmssink; then
  SINK="kmssink force-modesetting=true"
else
  SINK="autovideosink"
fi

# Colour conversion: the i.MX 2D GPU if available
if has imxvideoconvert_g2d; then CONVERT="imxvideoconvert_g2d"; else CONVERT="videoconvert ! videoscale"; fi

echo "spooky-display: $URL -> $SINK"
while true; do
  if has souphttpsrc; then
    # shellcheck disable=SC2086  # SINK/CONVERT are intentionally split into words
    gst-launch-1.0 -q souphttpsrc location="$URL" is-live=true timeout=5 \
      ! multipartdemux ! jpegdec ! $CONVERT ! $SINK
  elif command -v curl >/dev/null 2>&1; then
    # No HTTP source plugin in this image: let curl fetch the stream instead
    # shellcheck disable=SC2086
    curl -sN --connect-timeout 5 "$URL" | gst-launch-1.0 -q fdsrc fd=0 \
      ! multipartdemux ! jpegdec ! $CONVERT ! $SINK
  else
    echo "spooky-display: need GStreamer's souphttpsrc plugin or curl" >&2
    exit 1
  fi
  echo "spooky-display: stream ended or Pi not reachable; retrying in 2 s" >&2
  sleep 2
done

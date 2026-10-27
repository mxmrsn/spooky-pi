#!/usr/bin/env bash
# Everything a fresh Raspberry Pi OS (64-bit, with desktop) needs for the demo. Safe to
# run again. Usually run by scripts/pc/setup-new-pi.sh from your PC; by hand:
#
#   bash scripts/pc/deploy.sh && ssh -t spooky-pi@spooky-pi.local "sudo bash ~/spooky/scripts/pi/pi-setup.sh"
#
#  1. System packages (needs internet the first time)
#  2. Python venv in ~/spooky/.venv with the spooky package installed (needs internet the first time)
#  3. Teensy udev rules, so the show and scripts/pc/teensy-flash.sh can use it without sudo
#  4. Linger: the user's services run at boot without waiting for a login
#  5. The monitor's HDMI port forced on at boot (video=HDMI-A-1:...D in cmdline.txt), so the
#     desktop and the kiosk come up even if the monitor is off or plugged in later.
#     HDMI1 instead of HDMI0: HDMI_PORT=HDMI-A-2 ...; other mode: HDMI_MODE=1280x720M@60 ...;
#     skip it: FORCE_HDMI=0 ...
#  6. The show starts at boot, and the HDMI kiosk shows the visitor screen at every login
#  7. Ethernet becomes the show network: 192.168.77.1/24 with no gateway, so Wi-Fi stays the
#     route to the internet. Applies after the reboot, so an SSH session over Ethernet survives.
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo:  sudo bash $0"
  exit 1
fi

USER_NAME="${SUDO_USER:-spooky-pi}"
USER_ID=$(id -u "$USER_NAME")
PI_ADDR="192.168.77.1/24"
CMDLINE=/boot/firmware/cmdline.txt
HDMI_PORT="${HDMI_PORT:-HDMI-A-1}"  # HDMI-A-1 = HDMI0 (next to USB-C power), HDMI-A-2 = HDMI1
HDMI_MODE="${HDMI_MODE:-1920x1080M@60}"
PACKAGES="python3-venv python3-pygame python3-serial ffmpeg chromium curl grim pipewire-bin teensy-loader-cli"
as_user() { runuser -u "$USER_NAME" -- env XDG_RUNTIME_DIR="/run/user/$USER_ID" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$USER_ID/bus" "$@"; }
need_online() {
  getent hosts deb.debian.org >/dev/null && getent hosts pypi.org >/dev/null && return 0
  echo "   This step needs internet. Connect the Pi (Wi-Fi, or Ethernet to a router) and run this again."
  exit 1
}

echo "== 1. System packages"
missing=""
for p in $PACKAGES; do
  dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed" || missing="$missing $p"
done
if [ -n "$missing" ]; then
  need_online
  apt-get update -q
  # shellcheck disable=SC2086
  apt-get install -y -q $missing
else
  echo "   all installed"
fi

echo "== 2. Python environment"
[ -x .venv/bin/python ] || { need_online; as_user python3 -m venv --system-site-packages .venv; }
if getent hosts pypi.org >/dev/null; then
  as_user .venv/bin/pip install -q -e .  # also picks up new dependencies on a rerun
  echo "   spooky installed in .venv (commands: spooky, spooky-studio, spooky-eyes)"
elif as_user .venv/bin/python -c "import cv2, numpy, serial, spooky" 2>/dev/null; then
  echo "   offline: kept the existing .venv"
else
  need_online
fi

echo "== 3. Teensy access"
cat > /etc/udev/rules.d/00-teensy.rules <<'RULES'
# Teensy (PJRC): open to all users, and keep ModemManager off its serial port
ATTRS{idVendor}=="16c0", ATTRS{idProduct}=="04[789B]?", ENV{ID_MM_DEVICE_IGNORE}="1", ENV{ID_MM_PORT_IGNORE}="1"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="16c0", ATTRS{idProduct}=="04[789ABCD]?", MODE:="0666"
KERNEL=="hidraw*", ATTRS{idVendor}=="16c0", ATTRS{idProduct}=="04[789ABCD]?", MODE:="0666"
RULES
udevadm control --reload-rules && udevadm trigger
usermod -aG dialout,video "$USER_NAME"
echo "   udev rules in /etc/udev/rules.d/00-teensy.rules"

echo "== 4. Services run at boot"
loginctl enable-linger "$USER_NAME"
for _ in $(seq 10); do [ -S "/run/user/$USER_ID/bus" ] && break; sleep 1; done
echo "   linger enabled for $USER_NAME"

echo "== 5. $HDMI_PORT always on"
if [ "${FORCE_HDMI:-1}" = 0 ]; then
  echo "   skipped (FORCE_HDMI=0)"
else
  want="video=${HDMI_PORT}:${HDMI_MODE}D"
  if grep -q "$want" "$CMDLINE"; then
    echo "   already set: $want"
  else
    [ -f "$CMDLINE.bak-spooky" ] || cp "$CMDLINE" "$CMDLINE.bak-spooky"
    sed -i -E 's/ ?video=HDMI-A-[12]:[^ ]*//g; 1 s|$| '"$want"'|' "$CMDLINE"  # one forced port only
    echo "   added $want to cmdline.txt (original: $CMDLINE.bak-spooky)"
  fi
fi

echo "== 6. Show at boot, visitor screen on HDMI"
as_user bash scripts/pi/spooky-mode.sh show || echo "   (the show will start properly after the reboot)"
as_user bash scripts/pi/spooky-mode.sh kiosk on

echo "== 7. Ethernet show network"
CON=$(nmcli -t -f NAME,TYPE con show | awk -F: '$2=="802-3-ethernet"{print $1; exit}')
if [ -z "$CON" ]; then
  CON=spooky-show-net
  nmcli con add type ethernet ifname eth0 con-name "$CON" >/dev/null
fi
nmcli con modify "$CON" ipv4.method manual ipv4.addresses "$PI_ADDR" ipv4.gateway "" \
  ipv4.never-default yes ipv6.method link-local connection.autoconnect yes
echo "   '$CON': eth0 = $PI_ADDR after the reboot (i.MX should be 192.168.77.2)"

echo
read -r -p "Setup done. Reboot now? [Y/n] " ans
case "$ans" in n|N|no) echo "Reboot when you can: the HDMI and Ethernet changes need it." ;; *) echo "Rebooting..."; reboot ;; esac

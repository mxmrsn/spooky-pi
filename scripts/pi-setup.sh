#!/usr/bin/env bash
# One-time Pi setup that needs admin rights. Safe to run again. From your PC:
#
#   ssh -t spooky-pi@spooky-pi.local "sudo bash ~/spooky/scripts/pi-setup.sh"
#
#  1. core_freq_min=500 in config.txt: steady SPI clock for the NeoPixels (needs a reboot)
#  2. Ethernet (show network with the i.MX 8M Plus): fixed address 192.168.77.1/24, no gateway,
#     so Wi-Fi stays the route to the office network
#  3. Linger for the user: the show/Studio services start at boot even without a desktop login
set -euo pipefail

PI_ADDR="192.168.77.1/24"
CONFIG=/boot/firmware/config.txt
USER_NAME="${SUDO_USER:-spooky-pi}"
reboot_needed=no

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo:  sudo bash $0"
  exit 1
fi

echo "== 1. NeoPixel SPI clock"
if grep -q '^core_freq_min=' "$CONFIG"; then
  echo "   already set: $(grep '^core_freq_min=' "$CONFIG")"
else
  cp "$CONFIG" "$CONFIG.bak-spooky"
  printf '\n[all]\n# spooky-pi: keep the SPI clock steady for the WS2812B LEDs\ncore_freq_min=500\n' >> "$CONFIG"
  echo "   added core_freq_min=500 (backup: $CONFIG.bak-spooky)"
  reboot_needed=yes
fi

echo "== 2. Ethernet show network"
CON=$(nmcli -t -f NAME,TYPE con show | awk -F: '$2=="802-3-ethernet"{print $1; exit}')
if [ -z "$CON" ]; then
  CON=spooky-show-net
  nmcli con add type ethernet ifname eth0 con-name "$CON" >/dev/null
fi
nmcli con modify "$CON" ipv4.method manual ipv4.addresses "$PI_ADDR" ipv4.gateway "" \
  ipv4.never-default yes ipv6.method link-local connection.autoconnect yes
nmcli con up "$CON" >/dev/null 2>&1 || echo "   (no cable on eth0 right now; it applies when one is plugged in)"
echo "   '$CON': eth0 = $PI_ADDR (i.MX should be 192.168.77.2)"

echo "== 3. Services start at boot without a login"
loginctl enable-linger "$USER_NAME"
echo "   linger enabled for $USER_NAME"

echo
if [ "$reboot_needed" = yes ]; then
  read -r -p "Reboot now so the SPI change takes effect? [y/N] " ans
  case "$ans" in y|Y|yes) echo "Rebooting..."; reboot ;; *) echo "Remember to reboot before testing the LEDs." ;; esac
else
  echo "All set."
fi

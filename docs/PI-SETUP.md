# Setting up a Pi from a fresh SD card

About 20 minutes, most of it waiting. You need the Pi, its power supply, the HDMI monitor, an SD card (16 GB or more), and a computer with this repo cloned and an SSH key (`~/.ssh/id_ed25519.pub`; make one with `ssh-keygen -t ed25519` if you don't have one).

The Teensy keeps its firmware, so it needs nothing unless it's replaced (see the end).

## 1. Flash the card

In [Raspberry Pi Imager](https://www.raspberrypi.com/software/):

1. **Device:** Raspberry Pi 4. **OS:** Raspberry Pi OS (64-bit), the one *with desktop*. The kiosk needs the desktop.
2. **Customise** when asked:

   | Setting | Value |
   |---|---|
   | Hostname | `spooky-pi` |
   | Username / password | `spooky-pi` / a password your team knows |
   | Wi-Fi | a network with internet, plus your country (needed once, to install packages) |
   | Locale | your time zone and keyboard |
   | SSH | enabled, **public-key authentication**, paste the contents of your `~/.ssh/id_ed25519.pub` |

3. Write the card.

## 2. First boot

1. Plug in the monitor on **HDMI0** (the micro-HDMI port next to USB-C power), the camera, and the Teensy's USB. Then plug in the Pi's power.
2. Wait about 2 minutes. **The Raspberry Pi desktop should appear on the monitor.** If it doesn't, sort that out before going on: everything after this assumes the plain image can drive the screen.
3. Check you can reach it: `ssh spooky-pi@spooky-pi.local`. Use the same Wi-Fi as the Pi, or the Pi's Ethernet straight into your computer.

## 3. Run the setup

From your clone (on Windows, use Git Bash):

```bash
bash scripts/setup-new-pi.sh
```

1. **Connection:** it waits for the Pi. If the old card's host key is still in your `known_hosts`, it forgets it. It also adds your SSH key if needed.
2. **Code:** it copies the code to the Pi.
3. **Pi setup:** it runs [scripts/pi-setup.sh](../scripts/pi-setup.sh) on the Pi, which **asks for the Pi password once**:
   - installs the packages and the Python environment
   - sets up Teensy access
   - starts the show at boot
   - shows the visitor screen full-screen on HDMI0
   - forces HDMI0 on
   - makes Ethernet the 192.168.77.1 show network, the link to the i.MX
4. **Reboot:** press Enter to reboot.

## 4. Check it

About 1–2 minutes after the reboot:

- **Monitor:** the live camera with "Step closer... if you dare".
- **LEDs:** the glasses breathe red.
- **Web preview:** http://spooky-pi.local:8090/ shows the same screen, and `/camera` shows the camera with face boxes.
- **Status:** `ssh spooky-pi@spooky-pi.local "bash ~/spooky/scripts/spooky-mode.sh status"` shows `spooky-show` active and enabled, and the HDMI kiosk on.

Step in front of the camera for a full visit. Then make a backup card: [SD-BACKUP.md](SD-BACKUP.md).

## If something's off

| Symptom | Try |
|---|---|
| Setup says it needs internet | Connect the Pi to Wi-Fi (desktop network icon, or `sudo nmtui`), then run `bash scripts/setup-new-pi.sh` again. It's safe to rerun. |
| Desktop showed at first boot, monitor blank after setup | Undo the forced HDMI mode: `ssh -t spooky-pi@spooky-pi.local "sudo cp /boot/firmware/cmdline.txt.bak-spooky /boot/firmware/cmdline.txt && sudo reboot"`. To rerun the setup later without it, add `FORCE_HDMI=0` after `sudo`. |
| No LEDs | `spooky-mode.sh log` should show `Teensy: spooky-teensy …`. If it doesn't, check the Teensy's USB and its 5 V brick. |
| Show runs but no camera image | `spooky-mode.sh restart`; the log says if the camera can't be opened. |
| See the bare desktop | `spooky-mode.sh kiosk off` (and `kiosk on` to bring it back). |

**Replacing the Teensy:** plug it into your computer and run `bash scripts/teensy-flash.sh --here`. This needs `arduino-cli` and the Teensy core; see [hardware/BOM.md](../hardware/BOM.md).

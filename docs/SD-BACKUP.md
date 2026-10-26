# Backing up the Pi's SD card

The whole Pi lives on its SD card: Raspberry Pi OS, the spooky software, settings, network config and photos. A backup card is an exact copy you can swap in if the card dies.

## How cloning works

```
Pi's SD card ──Read──▶ 64 GB .img on your PC ──shrink (WSL)──▶ ~25 GB .img ──Write──▶ backup SD card (32 GB is fine)
```

- **Every byte is copied.** That includes the partition table and both partitions: the small `bootfs` (FAT32, which Windows can read) and the big `rootfs` (ext4, which Windows can't). So the copy is identical down to the hostname, passwords and SSH keys.
- **The `.img` file is a second backup.** Keep it, and you can make another card from it at any time.
- **Shut the Pi down first.** Copying a running system can catch files half-written.
- **The raw image is as big as the whole card** (64 GB, empty space included), even though the Pi only uses about 7 GB.
- **Shrinking makes it fit a smaller card.** The main partition is cut down to about 24 GB, so the backup fits a **32 GB** card. Without shrinking, the backup card must be at least 63,864,569,856 bytes.

## Steps (Windows, Win32 Disk Imager)

Install **Win32 Disk Imager** from its official SourceForge page (search "win32diskimager sourceforge"). Allow about an hour in total.

1. **Shut the Pi down.** This asks for the Pi password:
   ```
   ssh -t spooky-pi@spooky-pi.local "sudo poweroff"
   ```
   Wait until the green LED stops flashing (about 10 s), then unplug the power and take out the card.
2. **Put the Pi's card in the PC's card reader.**
   - ⚠️ **If Windows says "You need to format the disk", click Cancel.** It can't read the Linux partition; formatting would erase it.
   - The card shows up as a drive called **bootfs**. Note its drive letter.
3. **Read the card to a file.** Open Win32 Disk Imager (run as administrator):
   - **Image File:** e.g. `C:\spooky-backups\spooky-pi-2026-10-22.img` (make the folder first).
   - **Device:** the **bootfs** drive letter. Double-check it.
   - Leave *Read Only Allocated Partitions* off, since the main partition fills the whole card anyway.
   - Click **Read**. It takes about 15–40 minutes for 64 GB.
4. **Shrink the image** to fit a 32 GB card. This runs in WSL Ubuntu with Ubuntu's own tools (`e2fsck`, `resize2fs`, `parted`):
   ```
   wsl -d Ubuntu -u root bash /mnt/c/Users/<you>/Documents/code/spooky-pi/scripts/pc/shrink-image.sh /mnt/c/spooky-backups/spooky-pi-2026-10-22.img 24G
   ```
   It writes `...-24G.img` next to the original and leaves the original untouched.
5. **Swap in the backup card**, again clicking **Cancel** on any format prompts. If it's brand new it may show as a blank drive; that's fine.
6. **Write the image to the backup card.**
   - **Image file:** the shrunk `-24G.img`. Set **Device** to the backup card's drive letter; ⚠️ everything on it will be overwritten.
   - Click **Write**, then about 20–60 minutes.
   - If it says the card is too small, stop and ask: the image can be shrunk to fit.
7. **Optional but recommended:** click **Verify Only** to compare the card with the image.
8. **Label both cards** (e.g. "spooky MAIN" / "spooky BACKUP 10-22"), put the **original** back in the Pi, and power it up. The show (or the Studio, whichever mode was set) starts by itself.

## Using the backup

- **If the main card dies:** power off, insert the backup card, power on. It boots exactly as the Pi was on the day of the backup.
- **Refresh it after big changes:** for example after the final setup before the event, by repeating steps 1–8.
- **One card at a time:** never run two Pis from copies of the same card on the same network. They'd share a hostname and addresses.

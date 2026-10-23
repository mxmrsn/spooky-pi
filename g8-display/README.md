# G8 display: Halloween teaser loop

The G8 display (an i.MX 8M Plus running PHYTEC's ampliPHY Yocto image with a Weston desktop) plays the BBeviL Halloween teaser full-screen, on a loop, with the volume at maximum. It starts at boot and needs no Pi or network.

| | |
|---|---|
| Screen | built-in LVDS panel, 1024×768 (HDMI unused) |
| Video | `BBeviL_Halloween_Teaser_2.mp4`: H.264 1024×768 30 fps + AAC stereo, 19 s, decoded by the i.MX VPU |
| Player | `loop_teaser.py`: GStreamer `playbin` into a full-screen GTK window, cursor hidden |
| Boot service | `bbevil-teaser.service`, runs as the `weston` user |
| Sound | the on-board codec (`snd-card`, tlv320aic3x) through PulseAudio |

## Files

| File | Goes to (on the G8) |
|---|---|
| `BBeviL_Halloween_Teaser_2.mp4` | `/root/BBeviL_Halloween_Teaser_2.mp4` |
| `loop_teaser.py` | `/root/loop_teaser.py` |
| `bbevil-teaser.service` | `/etc/systemd/system/bbevil-teaser.service` |

To play a different video, change `URI` at the top of `loop_teaser.py`.

## Setup (once, from a PC on the same network)

Replace `10.0.7.79` with the G8's address.

1. **Copy the files:**
   ```sh
   scp BBeviL_Halloween_Teaser_2.mp4 loop_teaser.py root@10.0.7.79:/root/
   scp bbevil-teaser.service root@10.0.7.79:/etc/systemd/system/
   ```
2. **Let the `weston` user read them** (the player runs as `weston`, which owns the screen and the sound server):
   ```sh
   ssh root@10.0.7.79 'chmod o+x /root && chmod o+r /root/BBeviL_Halloween_Teaser_2.mp4 && chmod 755 /root/loop_teaser.py'
   ```
3. **Turn the sound card up to maximum and save it** (restored at boot by `alsa-restore`). Check the card number with `aplay -l`: it can change between boots, so the command picks it by name:
   ```sh
   ssh root@10.0.7.79 'for c in PCM "HP DAC" "Line DAC" "HPCOM DAC" HP Line HPCOM Class-D; do amixer -q -c sndcard sset "$c" 100% unmute 2>/dev/null || amixer -q -c sndcard sset "$c" 100%; done; alsactl store'
   ```
   The PulseAudio volume is set to 100% by the service itself every time it starts, because this image doesn't keep PulseAudio settings across reboots.
4. **Stop the Sciton UI from taking the screen**, then start the teaser now and at every boot:
   ```sh
   ssh root@10.0.7.79 'systemctl disable --now sciton-UI && systemctl daemon-reload && systemctl enable --now bbevil-teaser'
   ```
5. **Check it:**
   ```sh
   ssh root@10.0.7.79 'systemctl status bbevil-teaser --no-pager; journalctl -u bbevil-teaser -b --no-pager | tail'
   ```

## Everyday use

| You want to… | Run |
|---|---|
| Stop the teaser | `ssh root@10.0.7.79 'systemctl stop bbevil-teaser'` |
| Start it again | `ssh root@10.0.7.79 'systemctl start bbevil-teaser'` |
| Pick up a new video or script | `ssh root@10.0.7.79 'systemctl restart bbevil-teaser'` |
| Go back to the normal Sciton UI | `ssh root@10.0.7.79 'systemctl disable --now bbevil-teaser && systemctl enable sciton-UI && systemctl reboot'` |

**Behaviour:**
- **Looping:** the video seeks back to the start at the end, so there's no gap or flash of the desktop between loops.
- **Crashes:** if the player exits, systemd starts it again after 2 s.
- **Audio at boot:** the service waits up to 10 s for the `weston` user's PulseAudio, then sets every output to 100% and unmuted before playing.

## Why not `gst-launch-1.0 … waylandsink fullscreen=true`?

The GStreamer on this image (1.24.0) fails with `Window has no size set` when `waylandsink` is asked to go full-screen under Weston's desktop shell. `loop_teaser.py` uses `gtkwaylandsink` inside a GTK window that it makes full-screen instead. Plain `waylandsink` without `fullscreen=true` does play, but in an ordinary window.

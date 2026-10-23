# G8 display: Halloween teaser loop

The G8 display (an i.MX 8M Plus running PHYTEC's ampliPHY Yocto image with a Weston desktop) plays the BBeviL Halloween teaser full-screen, on a loop, loud but without distortion. It starts at boot and needs no Pi or network.

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
3. **Set the sound levels and save them** (restored at boot by `alsa-restore`). The card is picked by name (`sndcard`) because its number can change between boots:
   ```sh
   ssh root@10.0.7.79 'amixer -q -c sndcard sset PCM 100% && amixer -q -c sndcard sset "Line DAC" 100% && amixer -q -c sndcard sset "HP DAC" 100% && amixer -q -c sndcard sset "HPCOM DAC" 100% && amixer -q -c sndcard sset Line 0 unmute && amixer -q -c sndcard sset HP 0 unmute && amixer -q -c sndcard sset HPCOM 0 unmute && amixer -q -c sndcard sset Class-D 2 && alsactl store'
   ```

   | Control | Setting | Why |
   |---|---|---|
   | `PCM`, `* DAC` | 0 dB | no digital gain; PulseAudio trims `PCM` to −4 dB at start |
   | `Line`, `HP`, `HPCOM` (output drivers) | 0 dB | their +9 dB boost distorts |
   | `Class-D` (speaker amp) | `2` = +12 dB | loud and clear; `3` (+18 dB) distorts the laughs |

   **Don't set everything to 100%.** The clip is mastered to full scale (peaks at −0.1 dBFS), so the extra +9 dB driver and +18 dB amp gain clip it badly, worst on the laughs. The service sets the PulseAudio volume to 85% (−4 dB) every time it starts, which leaves headroom for those peaks. It does this on every start because this image doesn't keep PulseAudio settings across reboots.
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
- **Audio at boot:** the service waits up to 10 s for the `weston` user's PulseAudio, then sets every output to 85% (−4 dB) and unmuted before playing.
- **Louder or quieter:** keep `Class-D` at `2` and change the `85%%` in the service's `ExecStartPre` line (in small steps, e.g. 80% or 90%), then `systemctl daemon-reload && systemctl restart bbevil-teaser`. To try a level without restarting: `su weston -s /bin/sh -c "XDG_RUNTIME_DIR=/run/user/1000 pactl set-sink-volume @DEFAULT_SINK@ 90%"`.

## Why not `gst-launch-1.0 … waylandsink fullscreen=true`?

The GStreamer on this image (1.24.0) fails with `Window has no size set` when `waylandsink` is asked to go full-screen under Weston's desktop shell. `loop_teaser.py` uses `gtkwaylandsink` inside a GTK window that it makes full-screen instead. Plain `waylandsink` without `fullscreen=true` does play, but in an ordinary window.

# i.MX 8M Plus: animations on the Pi's triggers

The i.MX 8M Plus is a separate Linux board with **its own display**. It plays its own animations. The Pi doesn't send it video. It sends a short trigger on each step of a visit, naming the animation to play now. The Pi's camera feed and scary photo stay on the Pi's own HDMI screen.

```
Pi 4 (192.168.77.1) ──Ethernet── switch ──Ethernet── i.MX 8M Plus (192.168.77.2) ── its display
   └─ HDMI0: visitor screen (camera, countdown, before/after)
```

## The trigger

One UDP datagram to `192.168.77.2:5005`, containing a JSON object:

```json
{"cmd": "play", "animation": "reveal", "state": "REVEAL", "seq": 12}
```

| Field | Meaning |
|---|---|
| `animation` | what to play now |
| `state` | the show state that caused it, or `null` for a manual trigger |
| `seq` | counts up from 1 each time the show starts |

Nothing is sent back, and the show carries on whether or not the i.MX is listening.

**When each animation is sent:** the show sends one on entering each state. By default the name is the state in lower case:

| Show state | Animation | Moment |
|---|---|---|
| IDLE | `idle` | waiting for someone, and after each visit |
| AWAKE | `awake` | a face has appeared |
| WATCHING | `watching` | eyes lock on |
| COUNTDOWN | `countdown` | 3 s countdown to the photo |
| CAPTURE | `capture` | photo taken |
| PROCESSING | `processing` | scary version being made (~2 s) |
| REVEAL | `reveal` | before/after appears on the Pi's screen |
| SHOWING | `showing` | before/after stays up |

Rename or silence any of them in `[imx] animations` in the Pi's `spooky.toml`; `""` sends nothing for that state. `[imx] host` and `port` set where the triggers go; an empty `host` turns them off.

## Setup on the i.MX (once, as root)

1. **Fixed address on the show network** (systemd-networkd images):
   ```sh
   cp 10-spooky.network /etc/systemd/network/ && systemctl restart systemd-networkd
   ping -c 3 192.168.77.1
   ```
   On ConnMan or NetworkManager images, set `192.168.77.2/24`, with no gateway, there.
2. **Receive the triggers.** [spooky-trigger.py](spooky-trigger.py) is a reference receiver (Python 3, standard library only). It runs a command for each trigger, with `{animation}` filled in, and stops the previous one first:
   ```sh
   python3 spooky-trigger.py                                  # just print them
   python3 spooky-trigger.py --run "gst-play-1.0 --no-interactive /opt/spooky/{animation}.mp4"
   ```
   Any program that reads UDP port 5005 works instead.
3. **Start at boot:**
   ```sh
   cp spooky-trigger.py /usr/bin/ && cp spooky-trigger.service /etc/systemd/system/
   systemctl daemon-reload && systemctl enable --now spooky-trigger
   ```
   Edit `--run` in the service for your player. Match `XDG_RUNTIME_DIR` and `WAYLAND_DISPLAY` to `ls /run/user/*/wayland-*`.

## Testing

- **Send one by hand:** with the show running, run `python tools/eyes.py --imx reveal`, or `curl -X POST spooky-pi.local:8070/imx -d '{"animation": "reveal"}'`.
- **Watch the triggers without the i.MX:** run `python3 imx/spooky-trigger.py` on a laptop, with `[imx] host` set to the laptop's address.
- **The Pi's log** has a line for each trigger: `spooky-mode.sh log` shows `i.MX <- reveal`.

# spooky-pi

Evil doctor Halloween installation on a Raspberry Pi 4. PIR sensors wake it up, LED "glasses" (two 16-pixel rings plus a pupil each) react, the eyes follow your face, a countdown runs, the camera snaps you, [ScarySmile](ScarySmile/README.md) makes the photo scary, and the display reveals it with a scream.

Hardware, wiring and parts: [hardware/BOM.md](hardware/BOM.md).

## Running

On the Pi, from `~/spooky`:

```
.venv/bin/python -m spooky                 # the show, real hardware
.venv/bin/python -m spooky --sim all       # fully simulated (works over SSH)
.venv/bin/python -m spooky --sim leds,pir  # simulate some devices, use the rest for real
.venv/bin/python -m spooky.demo            # cycle LED scenes on the glasses
.venv/bin/python -m spooky.demo storm --sim  # preview one scene in the terminal
.venv/bin/python tools/focus_view.py       # live focus aid at http://spooky-pi.local:8000
.venv/bin/python tools/face_trigger.py     # camera + ScarySmile check, no show
.venv/bin/python -m pytest                 # tests (also run on Windows)
```

In simulation, type `1` or `2` and Enter to fire a PIR sensor, `f` to toggle a face in front of the fake camera (it uses your earlier captures), and `q` to quit. LEDs are drawn in the terminal and the display is written to `captures/display.jpg`.

A device that fails to start (e.g. the camera is unplugged) is logged and replaced by a stand-in, so the show keeps running with what works.

From Windows, `./deploy.sh` (Git Bash) copies the code to the Pi. `./deploy.sh --setup` also creates the venv and installs the requirements.

## Layout

| Path | What |
|---|---|
| `spooky/show.py` | State machine: IDLE → AWAKE → WATCHING → COUNTDOWN → CAPTURE → PROCESSING → REVEAL → SHOWING |
| `spooky/scenes.py` | Named LED looks (rings effect + pupils effect), and which scene each state uses |
| `spooky/effects.py` | Effect building blocks: Breathe, Comet, Fill, Strobe, Flicker, Sparkle, Lightning, Rainbow, Gaze, Blend, Sequence |
| `spooky/layout.py` | Glasses geometry for effects; maps logical pixels to the physical chain; brightness, gamma, current cap |
| `spooky/hw/` | Devices and their stand-ins: LEDs over SPI, PIRs, aiming LED, sounds, display, camera and face watcher |
| `spooky/config.py` | All settings; override them in `spooky.toml` (see `spooky.example.toml`) |
| `sounds/<event>/` | Drop sound files here, see [sounds/README.md](sounds/README.md) |
| `media/idle.jpg` | Optional attract screen shown between scares |

## Bring-up checklist when the hardware arrives

1. `sudo nano /boot/firmware/config.txt`, add `core_freq_min=500` (keeps the Pi 4's SPI clock steady for the NeoPixels), reboot.
2. `python -m spooky.demo --brightness 0.1` with one ring connected. If the colours are wrong or the animation runs backwards or rotated, adjust `leds.ring_offset` / `ring_clockwise` / `chain` in `spooky.toml` until the `awake` comets meet at the bottom of both eyes.
3. Check the eye tracking. If the eyes look away from you in `watching`, set `camera.gaze_mirror = false`.
4. PIRs: the Adafruit 189 has sensitivity and hold-time pots, plus a retrigger jumper (set it to retrigger).
5. Watch `est. LED current` in the demo and lower `brightness` or `max_current_a` if the USB brick sags.

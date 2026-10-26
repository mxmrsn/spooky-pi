# spooky-pi 🎃

A Halloween photo booth on a Raspberry Pi 4. LED "glasses" (two 16-LED rings) watch for a face. When someone steps up, the eyes lock on, a countdown runs on screen, and the camera takes their photo. The screen then shows it next to a scary version for 15 s, and the booth goes back to waiting.

**Hardware:** a Pi 4 runs everything. A See3CAM USB camera spots faces. A Teensy 4.1 on the Pi's USB drives the LED rings. The visitor screen is a web page the Pi serves on port 8090: show it on the Pi's own HDMI (kiosk), or on an i.MX 8M Plus over Ethernet.

## Quick start

Assumes the hardware is connected and powered, and you can `ssh spooky-pi@spooky-pi.local` (add your key with `ssh-copy-id spooky-pi@spooky-pi.local`).

1. **Copy the code to the Pi.** From your clone (on Windows, use Git Bash):
   ```bash
   ./deploy.sh --setup
   ```
   Leave out `--setup` after the first time.

2. **Start the show.** From then on it also starts by itself whenever the Pi powers up, after waiting up to 45 s for the Teensy and the camera:
   ```bash
   ssh spooky-pi@spooky-pi.local "bash ~/spooky/scripts/spooky-mode.sh show"
   ```

3. **Open the web preview:**

   | URL | Shows |
   |---|---|
   | http://spooky-pi.local:8090/ | the visitor screen, exactly what the display shows |
   | http://spooky-pi.local:8090/camera | the raw camera, with detected faces boxed and scored |

   If you're on the Pi's direct Ethernet link and those don't load, forward the ports over SSH and use `localhost:8090` instead:
   ```bash
   ssh -N -L 8090:localhost:8090 -L 8070:localhost:8070 spooky-pi@spooky-pi.local
   ```

4. **Step in front of the camera.** A face held for half a second starts a visit. A face still in view after a visit starts the next one 6 s later.

Watch it from the logs with `ssh spooky-pi@spooky-pi.local "bash ~/spooky/scripts/spooky-mode.sh log"`.

## Day to day

| To… | Run |
|---|---|
| Push code changes to the Pi | `./deploy.sh`, then `ssh spooky-pi@spooky-pi.local "bash ~/spooky/scripts/spooky-mode.sh restart"` |
| See what's running | `spooky-mode.sh status` (on the Pi) |
| Stop it | `spooky-mode.sh off` |
| Show the visitor screen on the Pi's own HDMI | `spooky-mode.sh kiosk on` (full-screen browser, also at every login; `kiosk off` to stop) |
| Drive the eyes from your code | HTTP API on port 8070: see [docs/EYES.md](docs/EYES.md), or `python tools/eyes.py rage --seconds 5` |
| Hear the Pi's audio on your PC | `python tools/listen.py` (needs `pip install sounddevice`) |
| Run without any hardware | `python -m spooky --sim all` (type `f` for a face, `q` to quit) |
| Run the tests | `python -m pytest` |

The show is silent until you add sound clips: [sounds/README.md](sounds/README.md).

## Where things live

| Path | What |
|---|---|
| `spooky/show.py` | the state machine: when the eyes wake, lock on, count down, snap and reveal |
| `spooky/scenes.py` | the eye states (LED looks) and which one each show state uses |
| `spooky/config.py` | every setting and its default; override any of them in `spooky.toml` (copy `spooky.example.toml`) |
| `spooky/control.py` | the eye/show control API |
| `spooky/hw/` | camera, display stream, LEDs (`teensy.py`), audio |
| `teensy/` | Teensy firmware (`bash scripts/teensy-flash.sh` builds and flashes it) |
| `tools/` | bring-up and debugging helpers (`led_test.py`, `focus_view.py`, `face_trigger.py`, …) |

## More docs

- [docs/EYES.md](docs/EYES.md): the state machine, every eye state, the control API, and how to tune them
- [docs/ARTISTS.md](docs/ARTISTS.md): Spooky Studio (port 8080), a browser tool for making LED scenes and adding voices. Run `spooky-mode.sh studio`; it can't run at the same time as the show.
- [hardware/BOM.md](hardware/BOM.md): wiring, the Teensy and parts
- [imx/README.md](imx/README.md): setting up the display computer
- [docs/SD-BACKUP.md](docs/SD-BACKUP.md): backing up the Pi's SD card
- First-time Pi setup (network, Teensy loader, boot services): `ssh -t spooky-pi@spooky-pi.local "sudo bash ~/spooky/scripts/pi-setup.sh"`

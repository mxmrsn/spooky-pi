# spooky-pi 🎃

A Halloween photo booth on a Raspberry Pi 4. LED "glasses" (two 16-LED rings) watch for a face. When someone steps up, the eyes lock on, a countdown runs on screen, and the camera takes their photo. The screen then shows it next to a scary version for 15 s, and the booth goes back to waiting.

**Hardware:** a Pi 4 runs the show. A See3CAM USB camera spots faces. A Teensy 4.1 on the Pi's USB drives the LED rings. The Pi's own HDMI monitor shows the visitor screen (camera, countdown, before/after), which is also a web page on port 8090. A separate i.MX 8M Plus with its own display plays animations when the Pi tells it to, over Ethernet.

## Quick start

Assumes the Pi is already set up (fresh SD card? follow [docs/PI-SETUP.md](docs/PI-SETUP.md) first), the hardware is connected and powered, and you can `ssh spooky-pi@spooky-pi.local`.

1. **Copy the code to the Pi.** From your clone (on Windows, use Git Bash):
   ```bash
   bash scripts/pc/deploy.sh
   ```

2. **Start the show.** From then on it also starts by itself whenever the Pi powers up, after waiting up to 45 s for the Teensy and the camera:
   ```bash
   ssh spooky-pi@spooky-pi.local "bash ~/spooky/scripts/pi/spooky-mode.sh show"
   ```

3. **Open the web preview:**

   | URL | Shows |
   |---|---|
   | http://spooky-pi.local:8090/ | the visitor screen, exactly what the display shows |
   | http://spooky-pi.local:8090/camera | the raw camera, with detected faces boxed and scored |

   If you're on the Pi's direct Ethernet link and those don't load, forward the ports over SSH and use `localhost:8090` instead:
   ```bash
   ssh -N -L 8090:localhost:8090 spooky-pi@spooky-pi.local
   ```

4. **Step in front of the camera.** A face held for half a second starts a visit. A face still in view after a visit starts the next one 6 s later.

Watch it from the logs with `ssh spooky-pi@spooky-pi.local "bash ~/spooky/scripts/pi/spooky-mode.sh log"`.

## Day to day

| To… | Run |
|---|---|
| Push code changes to the Pi | `bash scripts/pc/deploy.sh`, then `ssh spooky-pi@spooky-pi.local "bash ~/spooky/scripts/pi/spooky-mode.sh restart"` |
| See what's running | `spooky-mode.sh status` (on the Pi) |
| Stop it | `spooky-mode.sh off` |
| Show the visitor screen on the Pi's own HDMI | `spooky-mode.sh kiosk on` (full-screen browser, also at every login; `kiosk off` to stop) |
| Drive the eyes from your code | the control API at `:8090/api`: see [docs/EYES.md](docs/EYES.md), or `spooky-eyes rage --seconds 5` |
| Trigger an i.MX animation by hand | `spooky-eyes --imx reveal` |
| Hear the Pi's audio on your PC | `python -m spooky.tools.listen` (needs `pip install -e ".[listen]"`) |

The show is silent until you add sound clips: [sounds/README.md](sounds/README.md).

## Developing

```bash
pip install -e ".[dev]"        # the spooky package, its commands, pytest and ruff
spooky --sim all               # the whole show without hardware: type f for a face, q to quit
python -m pytest && ruff check .
```

Commands: `spooky` (the show), `spooky-studio` (the artists' web tool), `spooky-eyes` (drive the eyes; without installing, `python -m spooky.tools.eyes` needs only the standard library). Bring-up and debugging helpers are in `spooky/tools/` and run as `python -m spooky.tools.<name>`. CI runs the tests and the linter on every push.

## Where things live

| Path | What |
|---|---|
| `spooky/show.py` | the state machine: when the eyes wake, lock on, count down, snap and reveal |
| `spooky/scenes.py`, `effects.py` | the eye states (LED looks) and which one each show state uses |
| `spooky/config.py` | every setting and its default; override any of them in `spooky.toml` (copy `spooky.example.toml`) |
| `spooky/web/` | the one web server on 8090: visitor screen, camera view, control API |
| `spooky/hw/` | camera, the visitor screen (`display.py`), LEDs (`teensy.py`), i.MX triggers (`imx.py`), speaker |
| `spooky/scare/` | the scary-smile effect (also a command-line tool: `python -m spooky.scare photo.jpg`) |
| `spooky/studio/` | Spooky Studio, the artists' web tool |
| `spooky/tools/` | bring-up and debugging helpers: `led_test`, `listen`, `focus_view`, `face_trigger`, `prep_audio`, … |
| `scripts/pi/` | runs on the Pi: setup, mode switching, kiosk, boot services |
| `scripts/pc/` | runs on your computer: deploy, new-Pi setup, Teensy flashing, SD-image shrinking |
| `teensy/` | Teensy firmware (`bash scripts/pc/teensy-flash.sh` builds and flashes it) |
| `imx/` | the i.MX 8M Plus side: trigger receiver and its boot service |

## More docs

- [docs/EYES.md](docs/EYES.md): the state machine, every eye state, the control API, and how to tune them
- [docs/ARTISTS.md](docs/ARTISTS.md): Spooky Studio (port 8080), a browser tool for making LED scenes and adding voices. Run `spooky-mode.sh studio`; it can't run at the same time as the show.
- [hardware/BOM.md](hardware/BOM.md): wiring, the Teensy and parts
- [imx/README.md](imx/README.md): the i.MX 8M Plus: the animation triggers it gets and a receiver to set up on it
- [docs/SD-BACKUP.md](docs/SD-BACKUP.md): backing up the Pi's SD card
- [docs/PI-SETUP.md](docs/PI-SETUP.md): setting up a Pi from a fresh SD card (`bash scripts/pc/setup-new-pi.sh` does the work)

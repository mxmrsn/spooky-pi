# spooky-pi 🎃

An evil doctor Halloween installation on a Raspberry Pi 4. Walk up and the doctor's LED glasses wake up and follow your face. A countdown runs, the camera snaps you, and a few seconds later you see yourself with a horrible grin, along with a scream and a word from the bosses.

![LED scenes, rendered from the code](docs/img/scenes.png)
<sub>Every LED scene over 2 seconds, rendered by `tools/render_scenes.py` from the same code that drives the glasses. Red labels are the show state that uses each scene.</sub>

## 🎨 For artists: Spooky Studio

Play with the glasses, sounds and show from a browser, with nothing to install: **http://spooky-pi.local:8080**. To start it, double-click **Start Spooky Studio** in [`launchers/`](launchers/README.md) (Windows `.cmd`, Mac `.command`).

<a href="docs/ARTISTS.md"><img src="docs/img/studio_glasses.png" alt="Spooky Studio" width="720"></a>

**[Artist guide →](docs/ARTISTS.md)**: build and save LED scenes with sliders, drop in voice recordings, hear the bosses with talking glasses, and run the show with big buttons.

**[Driving the eyes →](docs/EYES.md)**: for teammates integrating their own work: the show's state machine, every eye state, and an HTTP API (port 8070) to hold the eyes in any state or start/reset a visit.

---

## A visit, start to finish

![Sequence of a visit: camera, show, LEDs, speaker, display](docs/img/visit.png)

## Hardware

![Hardware block diagram](docs/img/hardware.png)

The LED glasses hang off a **Teensy 4.1** on the Pi's USB, so nothing plugs into the Pi's GPIO header. The Pi does all the animation and sends finished frames; the Teensy copies them onto the LEDs. **The camera wakes the show:** it watches while idle, and a face that stays half a second starts a visit. There are no PIRs, pupil LEDs or aiming LED in this build (the firmware still reads PIRs on pins 2/3 if they're ever fitted: set `[teensy] pir_pins = [2, 3]`).

| Signal | Teensy pin | | Power | Source |
|---|---|---|---|---|
| LED data (2 × 16-LED rings, one chain) | 1 | | Pi + camera | Pi 5 V / 3 A supply |
| (optional PIR 1 / PIR 2) | 2 / 3 | | Teensy (VIN) and LEDs | 5 V / 2.5 A USB brick |
| On-board LED: 1 Hz blink = running, 4 Hz = frames arriving | 13 | | Fan | Pi pins 4/6 |

Cut the Teensy's VUSB–VIN pad so the brick, not the Pi, powers it; the grounds are shared through USB. Flash the firmware with `bash scripts/teensy-flash.sh` (after `pi-setup.sh`). Wiring details and the older GPIO driver board (`[teensy] enabled = false`): **[hardware/BOM.md](hardware/BOM.md)**.

### Display: i.MX 8M Plus over Ethernet

![Display network](docs/img/display.png)

The show serves the screen as an MJPEG stream on port 8090. The i.MX pulls it with GStreamer and shows it full-screen, reconnecting whenever the Pi or show restarts. Setup for the i.MX: **[imx/README.md](imx/README.md)**.

## Software

![Software architecture: inputs, background threads, main loop, outputs](docs/img/software.png)

The rules that hold it together:
- **Everything runs off `Show.step(now)`.** Devices are polled each tick, so tests drive it with a fake clock.
- **Any device can be simulated (`--sim`).** A real device that fails to start is swapped for its stand-in, so the show runs with what works.
- **Animations never touch the wiring.** Effects see "left/right eye, angle, mirrored angle". `layout.py` maps that onto the chain order set in `spooky.toml`.

### Show states

<img src="docs/img/states.png" alt="Show state machine" width="300" align="right">

| State | LED scene | Sound event | Screen | Camera |
|---|---|---|---|---|
| IDLE | `idle` | `ambient` every 45–120 s | live feed: "Step closer... if you dare" | on: a face held 0.5 s wakes it |
| AWAKE | `awake` (1 s before lock-on) | `awaken` | live feed: "Step closer" | on |
| WATCHING | `watching`: eyes follow you, turn red as they lock on (2 s) | `spotted`, then `hold_still` at 1 s | live feed: "Step closer" if far, else "HOLD STILL!" | on |
| COUNTDOWN | `countdown` | `countdown` | live feed with a big 3, 2, 1 | on |
| CAPTURE | `flash` | `shutter` | white flash | on |
| PROCESSING | `processing` | | the photo: "Developing..." | off |
| REVEAL | `reveal` | `scream` | before and after, side by side | off |
| SHOWING | `showing` | `outro` | before and after (15 s with REVEAL) | off |

The timings come from `[show]` in `spooky.toml`. Each LED scene is pictured in the gallery at the top.

<br clear="right">

### Sounds and boss voices

![How a show event picks a sound effect and a boss line](docs/img/voices.png)

The countdown and flash scenes are never replaced, so visitors always see the timer. Folder layout, file tips and the recording workflow: **[sounds/README.md](sounds/README.md)**.

## How you interact with it

| You want to… | Run (on the Pi, in `~/spooky`, with `.venv/bin/python`) |
|---|---|
| Open the artist Studio | Double-click `launchers/Start Spooky Studio.*`, or on the Pi: `bash scripts/studio-ctl.sh start` (also `stop`, `status`, `log`) |
| Run the show | `python -m spooky` |
| Run it with no hardware | `python -m spooky --sim all` (type `f` = face, `1`/`2` = motion, `q` = quit) |
| Simulate only some parts | `python -m spooky --sim leds,pir` |
| Preview LED scenes | `python -m spooky.demo [scene …] [--sim] [--brightness 0.1]` |
| Check the sound library | `python -m spooky.audition list` |
| Hear a boss with their LEDs | `python -m spooky.audition play boss_a [--event scream] [--sim]` |
| Replay a state's cues | `python -m spooky.audition state REVEAL --times 3 [--voice boss_b]` |
| Add recordings | `python tools/prep_audio.py raw/*.m4a --voice boss_a --event spotted` |
| Test clips before real ones | `python tools/make_placeholders.py` (`--clean` removes them) |
| Focus the camera | `python tools/focus_view.py`, then open `http://spooky-pi.local:8000` |
| Camera-only check | `python tools/face_trigger.py` |
| Hold the eyes in a state | `python tools/eyes.py rage --seconds 5` (show running; see docs/EYES.md) |
| Check the LED chain | `python tools/led_test.py` (Studio/show stopped) |
| Check / tune PIR sensors, if fitted | `python tools/pir_scope.py` (live traces in a browser) or `python tools/pir_test.py` |
| Flash the Teensy firmware | `bash scripts/teensy-flash.sh` (from your PC; needs arduino-cli + the Teensy core) |
| Run tests | `python -m pytest` (also works on Windows) |
| Update the README figures | `python tools/render_scenes.py` (LED gallery), `python tools/render_diagrams.py` (diagrams; on a PC with Chrome or Edge) |

| File / folder | What you change there |
|---|---|
| `spooky.toml` | Settings (copy `spooky.example.toml`): LED wiring order, brightness, timings, display |
| `spooky/scenes.py` | Add or tweak LED looks, and pick which scene each state uses |
| `custom_scenes.json` | Scenes and moment choices saved by the Studio (plain JSON, in git) |
| `sounds/<event>/`, `sounds/voices/<boss>/` | Audio clips (not in git) and `voice.toml` per boss |
| `media/idle.jpg` | Optional attract screen between scares |
| `captures/` | Photos taken (on the Pi only, last 50 kept, never committed) |

## Running it on the Pi

**One-time admin setup** (asks for the Pi password; safe to rerun). It steadies the SPI clock for the LEDs, gives Ethernet its fixed show-network address, and lets services start without a login:
```
ssh -t spooky-pi@spooky-pi.local "sudo bash ~/spooky/scripts/pi-setup.sh"
```

**Pick what the Pi runs, now and after every reboot.** Only one can run at a time, because both use the lights, speaker and display:

| Command (on the Pi) | Runs |
|---|---|
| `bash ~/spooky/scripts/spooky-mode.sh studio` | Spooky Studio for the artists (**current mode**) |
| `bash ~/spooky/scripts/spooky-mode.sh show` | The real show: **use this for the event** |
| `bash ~/spooky/scripts/spooky-mode.sh off` | Neither |
| `bash ~/spooky/scripts/spooky-mode.sh status` | What's running, and what starts at boot |
| `bash ~/spooky/scripts/spooky-mode.sh restart` | Pick up new code after `./deploy.sh` |
| `bash ~/spooky/scripts/spooky-mode.sh log` | The running one's recent log (state changes, warnings) |

## Development

![Development workflow: PC, GitHub, Pi](docs/img/dev.png)

- **First time:** run `./deploy.sh --setup` (Git Bash). It creates the venv and installs `requirements.txt`.
- **Python:** 3.11+ locally, 3.13 on the Pi. `spidev`, `gpiozero`, `pyserial` and `pygame` come with Raspberry Pi OS.
- **Diagrams:** the source for each diagram is in `docs/diagrams/*.mmd` (Mermaid text). After editing, rerun `tools/render_diagrams.py` and commit the regenerated PNG/SVG in `docs/img/`.
- **Hardware bring-up:** follow the checklist at the bottom of [hardware/BOM.md](hardware/BOM.md), after running `pi-setup.sh` once.
- **SD card backup:** see [docs/SD-BACKUP.md](docs/SD-BACKUP.md). `tools/shrink-image.sh` makes the image fit a 32 GB card.
- **CI:** GitHub Actions runs the tests and checks the shell scripts on every push (`.github/workflows/tests.yml`).

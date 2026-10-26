# Driving the eyes: guide for teammates

The glasses are two 16-LED rings on one data chain (no pupil LEDs), driven by a Teensy on the Pi's USB. The Pi decides what they show. Each look is an **eye state** (a "scene" in the code). The **show** is a state machine that picks an eye state for each step of a visit. You can take over the eyes, or nudge the show, from your own code through a small HTTP API.

## The show's state machine

A face in the camera starts a visit; nothing else needs to happen.

| Show state | Starts when | Eye state | Screen |
|---|---|---|---|
| IDLE | at start, and after each visit | `idle` | live camera: "Step closer... if you dare" |
| AWAKE | a face stays 0.5 s (`wake_face_hold`) | `awake` | "Step closer" |
| WATCHING | 1 s later (`awaken_time`) | `watching` | "Step closer" / "HOLD STILL!" |
| COUNTDOWN | face held 2 s (`face_hold`) | `countdown` | big 3, 2, 1 |
| CAPTURE | 3 s later (`countdown`) | `flash` | white flash |
| PROCESSING | photo taken | `processing` | the photo: "Developing..." |
| REVEAL | scary version ready (~2 s) | `reveal` | before and after |
| SHOWING | 2.5 s later (`reveal`) | `showing` | before and after, until 15 s in total |

After a visit the show waits 6 s (`rearm`); a face still in view then starts the next visit (set `leave_between_visits = true` to make people step away first). The face leaving for 1.5 s (`face_lost_grace`) drops WATCHING or COUNTDOWN back to AWAKE. AWAKE with no face for 20 s (`awake_timeout`) goes back to IDLE. The timings live in `[show]` in `spooky.toml` (defaults in [spooky/config.py](../spooky/config.py)). The code is [spooky/show.py](../spooky/show.py).

## Eye states

| Eye state | Look |
|---|---|
| `idle` | slow red breathing |
| `awake` | two green comets circling |
| `watching` | a green spot that follows the visitor's face and turns red as it locks on |
| `countdown` | rings fill with soft white from 12 o'clock over 3 s |
| `flash` | soft white |
| `processing` | violet comets |
| `reveal` | slow, soft red strobe |
| `showing` | ember flicker |
| `off` | dark |
| `storm` | pale-blue lightning |
| `toxic_sparkle` | green breathing with white sparkles |
| `madness` | rainbow swirl |
| `possessed` | red comet, a burst of strobe, then breathing |
| `rage` | red flicker |
| `glare` | amber breathing |
| `venom` | slow green comets |

Scenes made in the Studio (saved to `custom_scenes.json`) are eye states too. `GET /eyes` lists everything available right now.

## Control API

The show serves it on port **8070** (`[control] port`). Use `spooky-pi.local:8070` on the same network, or `192.168.77.1:8070` on the show's Ethernet.

| Request | Does |
|---|---|
| `GET /eyes` | show state, current eye state, any hold, and every eye state |
| `POST /eyes {"state": "rage"}` | hold an eye state until cleared |
| `POST /eyes {"state": "rage", "seconds": 5}` | hold it for 5 s, then give the eyes back to the show |
| `POST /eyes {"state": null}` | give the eyes back to the show now |
| `POST /show {"action": "wake"}` | start a visit (from IDLE only) |
| `POST /show {"action": "reset"}` | drop the visit and go back to IDLE |

A hold overrides the show's own eye states, voice lines included, but the show keeps running underneath: the camera, screen and photo carry on. Bad requests get a 400 with an `error` message.

```bash
curl -s spooky-pi.local:8070/eyes
curl -s -X POST spooky-pi.local:8070/eyes -d '{"state": "rage", "seconds": 5}'
```

```python
import json, urllib.request

def eyes(state, seconds=None, host="spooky-pi.local:8070"):
    body = json.dumps({"state": state, "seconds": seconds}).encode()
    urllib.request.urlopen(urllib.request.Request(f"http://{host}/eyes", body))

eyes("glare", 3)
```

Or use the helper (standard library only): `python tools/eyes.py rage --seconds 5`, `python tools/eyes.py auto`, `python tools/eyes.py --wake`.

## Changing things

- **A new eye state:** add an entry to `SCENES` in [spooky/scenes.py](../spooky/scenes.py). A scene is a rings effect, plus a pupils effect that only shows on builds with pupil LEDs. The effects (`Solid`, `Breathe`, `Comet`, `Fill`, `Strobe`, `Flicker`, `Sparkle`, `Lightning`, `Rainbow`, `Gaze`, `Blend`, `Sequence`) are in [spooky/effects.py](../spooky/effects.py). Preview it with `python -m spooky.demo <name>`, or `--sim` to draw it in the terminal. Artists can also build scenes with sliders in the Studio.
- **Which eye state a show state uses:** pick it in the Studio's scene tab (saved to `custom_scenes.json`), or change `STATE_SCENES` in `scenes.py`.
- **Timings and prompts:** `[show]` in `spooky.toml`. The on-screen prompt texts are at the top of `show.py`.
- **Brightness:** `[leds] brightness` caps everything (0.4). `max_current_a` limits the total current draw. Flashes and strobes are deliberately dimmed (`SOFT_WHITE` / `SOFT_BLOOD` in `scenes.py`).

## Running and testing

- On the Pi: `bash ~/spooky/scripts/spooky-mode.sh show` (or `studio`, `off`, `status`, `log`).
- Visitor screen: `http://spooky-pi.local:8090/`. Camera with face boxes: `/camera`.
- Without hardware: `python -m spooky --sim all`. Type `f` for a face, `q` to quit. The control API works there too, on `localhost:8070`.
- Tests: `python -m pytest`.

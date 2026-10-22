"""Artist-made scenes, built from simple effect settings and saved to custom_scenes.json.

The Studio writes this file; the show loads it at start-up. It's plain JSON, so it
can also be edited by hand and lives in git:

    {
      "scenes": {
        "witch_eyes": {
          "rings":  {"effect": "Comet", "col": "#30ff00", "speed": 1.2, "tail": 0.5, "heads": 2, "mirror": true},
          "pupils": {"effect": "Breathe", "col": "#ff0000", "period": 1.5}
        }
      },
      "state_scenes": {"IDLE": "witch_eyes"}
    }

EFFECTS describes every effect the Studio offers: its settings, labels and ranges.
"""

import json
from pathlib import Path

from . import effects

FILE = Path(__file__).resolve().parent.parent / "custom_scenes.json"


def _c(key, label, default):
    return {"key": key, "label": label, "type": "color", "default": default}


def _n(key, label, lo, hi, default, step=0.01):
    return {"key": key, "label": label, "type": "number", "min": lo, "max": hi, "step": step, "default": default}


def _b(key, label, default):
    return {"key": key, "label": label, "type": "bool", "default": default}


EFFECTS = {
    "Solid": {"cls": effects.Solid, "help": "One steady colour.",
              "params": [_c("col", "Colour", "#ff0000"), _n("level", "Brightness", 0, 1, 1.0)]},
    "Breathe": {"cls": effects.Breathe, "help": "Slowly glows brighter and dimmer.",
                "params": [_c("col", "Colour", "#ff0000"), _n("period", "Seconds per breath", 0.3, 10, 4.0, 0.1),
                           _n("low", "Dimmest", 0, 1, 0.08), _n("high", "Brightest", 0, 1, 1.0)]},
    "Comet": {"cls": effects.Comet, "help": "Bright dots chase round the rings with fading tails.",
              "params": [_c("col", "Colour", "#30ff00"), _n("speed", "Speed (turns/s, minus = backwards)", -3, 3, 0.8),
                         _n("tail", "Tail length", 0.05, 1, 0.4), _n("heads", "Number of comets", 1, 4, 1, 1),
                         _b("mirror", "Mirror the two eyes", True), _c("background", "Background", "#000000")]},
    "Fill": {"cls": effects.Fill, "help": "Rings fill up from the top, then stay full.",
             "params": [_c("col", "Colour", "#ffffff"), _n("duration", "Seconds to fill", 0.5, 10, 3.0, 0.1),
                        _c("background", "Background", "#000000")]},
    "Strobe": {"cls": effects.Strobe, "help": "Flashes on and off.",
               "params": [_c("col", "Colour", "#ffffff"), _n("hz", "Flashes per second", 0.5, 20, 8.0, 0.5),
                          _n("duty", "Time on", 0.05, 0.95, 0.4), _c("background", "Background", "#000000")]},
    "Flicker": {"cls": effects.Flicker, "help": "Wobbles like fire or a candle.",
                "params": [_c("col", "Colour", "#ff3000"), _n("amount", "Wobble", 0, 1, 0.6),
                           _n("speed", "Speed", 0.1, 5, 1.0)]},
    "Sparkle": {"cls": effects.Sparkle, "help": "Random twinkles over a base colour.",
                "params": [_c("col", "Sparkle colour", "#ffffff"), _c("base", "Base colour", "#000000"),
                           _n("rate", "Sparkles per second", 0.5, 30, 6.0, 0.5), _n("decay", "Sparkle length", 0.05, 1, 0.15)]},
    "Lightning": {"cls": effects.Lightning, "help": "Dark, then sudden double flashes.",
                  "params": [_c("col", "Colour", "#a0d0ff"), _n("every", "Seconds between storms", 0.8, 10, 3.0, 0.1),
                             _c("background", "Background", "#000000")]},
    "Rainbow": {"cls": effects.Rainbow, "help": "All the colours, spinning.",
                "params": [_n("speed", "Speed", -2, 2, 0.3), _n("saturation", "Colourfulness", 0, 1, 1.0),
                           _b("mirror", "Mirror the two eyes", True)]},
    "Off": {"cls": effects.Off, "help": "Dark.", "params": []},
}


def schema():
    """EFFECTS without the classes, for the Studio page."""
    return {name: {"help": e["help"], "params": e["params"]} for name, e in EFFECTS.items()}


def build_effect(spec):
    """{"effect": "Comet", "col": "#ff0000", ...} -> effect instance. Unknown keys are ignored,
    numbers are clamped to their range and missing settings use the defaults."""
    name = spec.get("effect", "Off")
    if name not in EFFECTS:
        raise ValueError(f"Unknown effect {name!r}")
    kwargs = {}
    for p in EFFECTS[name]["params"]:
        v = spec.get(p["key"], p["default"])
        if p["type"] == "number":
            v = min(max(float(v), p["min"]), p["max"])
            if p["step"] == 1:
                v = int(round(v))
        elif p["type"] == "bool":
            v = bool(v)
        else:
            v = str(v)
            effects.rgb(v)  # raises on a bad colour
        kwargs[p["key"]] = v
    return EFFECTS[name]["cls"](**kwargs)


def build(spec):
    """Scene spec -> (rings effect, pupils effect)."""
    return build_effect(spec.get("rings", {})), build_effect(spec.get("pupils", spec.get("rings", {})))


def load(path=None):
    path = Path(path or FILE)
    if not path.is_file():
        return {"scenes": {}, "state_scenes": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"scenes": data.get("scenes", {}), "state_scenes": data.get("state_scenes", {})}


def save(data, path=None):
    path = Path(path or FILE)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)

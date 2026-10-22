import json
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest

from spooky import audio, scenes
from spooky.config import Config
from spooky.hw.leds import NullStrip
from spooky.layout import Layout
from spooky.studio.core import RecordingLeds, Studio, StudioError
from spooky.studio.server import make_server


class Player:
    def __init__(self):
        self.played, self.stopped = [], 0

    def play(self, path):
        self.played.append(path)

    def stop(self):
        self.stopped += 1


@pytest.fixture
def studio(tmp_path):
    cfg = Config()
    cfg.audio.folder = str(tmp_path / "sounds")
    cfg.captures = str(tmp_path / "captures")
    cfg.display.file_path = str(tmp_path / "display.jpg")
    t = np.arange(8000) / 8000
    audio.write_wav(tmp_path / "sounds" / "scream" / "aah.wav", 0.4 * np.sin(2 * np.pi * 300 * t), 8000)
    audio.write_wav(tmp_path / "sounds" / "voices" / "boss" / "spotted" / "hey.wav", 0.4 * np.sin(2 * np.pi * 150 * t), 8000)
    (tmp_path / "sounds" / "voices" / "boss" / "voice.toml").write_text('scene = "rage"\n')
    st = Studio(cfg, RecordingLeds(Layout(cfg.leds), NullStrip()), Player(), custom_path=tmp_path / "custom.json")
    st.raw_dir = tmp_path / "raw"
    yield st
    st.stop()
    scenes.load_custom(tmp_path / "nothing.json")  # put the global scene list back


SPEC = {"rings": {"effect": "Comet", "col": "#ff00ff", "speed": 2}, "pupils": {"effect": "Breathe", "col": "#00ff00"}}


def test_preview_renders_to_leds(studio):
    studio.preview("reveal")
    studio.tick()
    colors = studio.frame()
    assert len(colors) == 34 and all(c.startswith("#") and len(c) == 7 for c in colors)
    assert studio.status()["scene"] == "reveal"


def test_save_custom_scene_and_use_it_for_a_moment(studio, tmp_path):
    name = studio.save_scene("Witch Eyes!", SPEC)
    assert name == "witch_eyes" and name in scenes.SCENES
    saved = json.loads((tmp_path / "custom.json").read_text())
    assert saved["scenes"]["witch_eyes"]["rings"]["effect"] == "Comet"

    studio.set_state_scene("IDLE", "witch_eyes")
    assert scenes.STATE_SCENES["IDLE"] == "witch_eyes"
    studio.set_state_scene("IDLE", "idle")  # back to the original drops the override
    assert "IDLE" not in json.loads((tmp_path / "custom.json").read_text())["state_scenes"]

    studio.set_state_scene("REVEAL", "witch_eyes")
    studio.delete_scene("witch_eyes")
    assert "witch_eyes" not in scenes.SCENES and scenes.STATE_SCENES["REVEAL"] == "reveal"


def test_scene_mistakes_are_friendly_errors(studio):
    with pytest.raises(StudioError, match="built-in"):
        studio.save_scene("idle", SPEC)
    with pytest.raises(StudioError):
        studio.save_scene("x", {"rings": {"effect": "Solid", "col": "not a colour"}})
    with pytest.raises(StudioError):
        studio.preview_spec({"rings": {"effect": "Teleport"}})
    with pytest.raises(StudioError):
        studio.delete_scene("awake")


def test_effect_settings_are_clamped(studio):
    studio.preview_spec({"rings": {"effect": "Comet", "speed": 99, "heads": 2.7}})
    assert studio.scene.rings.speed == 3 and studio.scene.rings.heads == 3


def test_library_and_play_with_talking_scene(studio):
    lib = studio.library()
    ids = sorted(c["id"] for c in lib["clips"])
    assert ids == ["scream/aah.wav", "voices/boss/spotted/hey.wav"]
    assert lib["voices"] == [{"name": "boss", "scene": "rage", "talk": "pupils", "weight": 1.0}]
    json.dumps(lib)  # must be JSON-safe (no numpy types)

    studio.play("voices/boss/spotted/hey.wav")
    assert studio.player.played and studio.overlay is not None
    with pytest.raises(StudioError):
        studio.play("../../secrets.txt")


def test_upload_delete_and_voices(studio, tmp_path):
    t = np.arange(4000) / 8000
    raw = tmp_path / "rec.wav"
    audio.write_wav(raw, 0.3 * np.sin(2 * np.pi * 200 * t), 8000)
    clip = studio.upload("My Line.wav", raw.read_bytes(), "hold_still", voice="New Boss")
    assert clip["voice"] == "new_boss" and clip["event"] == "hold_still"
    assert clip["id"].startswith("voices/new_boss/hold_still/my_line")
    again = studio.upload("My Line.wav", raw.read_bytes(), "hold_still", voice="New Boss")
    assert again["id"] != clip["id"]  # never overwrites
    assert any((tmp_path / "raw").iterdir())  # original kept

    with pytest.raises(StudioError):
        studio.upload("notes.txt", b"hi", "scream")
    with pytest.raises(StudioError):
        studio.upload("a.wav", raw.read_bytes(), "whenever")

    studio.delete_clip(clip["id"])
    assert (tmp_path / "sounds" / ".trash" / clip["id"]).is_file()
    assert clip["id"] not in [c["id"] for c in studio.library()["clips"]]

    studio.save_voice("new boss", scene="venom", talk="all", weight=2)
    v = next(v for v in studio.library()["voices"] if v["name"] == "new_boss")
    assert (v["scene"], v["talk"], v["weight"]) == ("venom", "all", 2.0)
    with pytest.raises(StudioError):
        studio.save_voice("x", talk="eyebrows")


def test_show_runs_from_buttons(studio):
    with pytest.raises(StudioError):
        studio.motion()
    studio.start_show("sim")
    studio.tick()
    assert studio.status()["state"] == "IDLE"
    studio.motion(0)
    studio.tick()
    assert studio.status()["state"] == "AWAKE"
    with pytest.raises(StudioError, match="running"):
        studio.preview("idle")
    studio.stop_show()
    assert studio.status()["mode"] == "preview"


def test_http_api(studio):
    server = make_server(studio, host="127.0.0.1", port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(path, body):
        req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req))

    try:
        info = json.load(urllib.request.urlopen(base + "/api/info"))
        assert "Comet" in info["effects"] and len(info["geometry"]) == 34
        assert b"Spooky Studio" in urllib.request.urlopen(base + "/").read()
        assert post("/api/preview", {"name": "storm"}) == {"ok": True}
        with pytest.raises(urllib.error.HTTPError) as e:
            post("/api/preview", {"name": "nope"})
        assert e.value.code == 400
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/../../spooky/config.py")
        assert e.value.code == 404
    finally:
        server.shutdown()
        server.server_close()

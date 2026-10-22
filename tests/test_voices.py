import random

import numpy as np
import pytest

from spooky import audio, scenes
from spooky.audition import library_report
from spooky.config import Config
from spooky.effects import Solid, Talk
from spooky.layout import Layout
from spooky.voices import VoiceBank, load_voice


class Player:
    def __init__(self):
        self.played = []

    def play(self, path):
        self.played.append(path)


def tone(path, seconds=1.0, gaps=False):
    t = np.arange(int(seconds * 8000)) / 8000
    x = 0.5 * np.sin(2 * np.pi * 220 * t)
    if gaps:  # loud / silent halves, so the envelope has shape
        x[len(x) // 2:] = 0
    audio.write_wav(path, x, 8000)
    return path


@pytest.fixture
def library(tmp_path):
    v = tmp_path / "voices"
    tone(v / "boss_a" / "awaken" / "hello.wav")
    tone(v / "boss_a" / "awaken" / "again.wav")
    tone(v / "boss_a" / "scream" / "noo.wav", 2.0)
    (v / "boss_a" / "voice.toml").write_text('scene = "glare"\ntalk = "all"\nweight = 3\n')
    tone(v / "boss_b" / "awaken" / "hey.wav")
    (v / "boss_b" / "voice.toml").write_text('scene = "rage"\n')
    return tmp_path


def test_clip_analysis(tmp_path):
    info = audio.analyse(tone(tmp_path / "a.wav", 2.0, gaps=True))
    assert info.duration == pytest.approx(2.0, abs=0.01)
    assert info.peak_db == pytest.approx(20 * np.log10(0.5), abs=0.1)
    n = len(info.envelope)
    assert n == pytest.approx(2.0 * audio.ENVELOPE_HZ, abs=2)
    assert info.envelope[: n // 2 - 2].min() > 0.9 and info.envelope[n // 2 + 2:].max() < 0.01


def test_voice_settings_and_lines(library):
    v = load_voice(library / "voices" / "boss_a")
    assert (v.scene, v.talk, v.weight) == ("glare", "all", 3.0)
    assert sorted(v.lines) == ["awaken", "scream"]
    assert len(v.lines["awaken"]) == 2


def test_bad_voice_settings_skipped(library):
    (library / "voices" / "boss_b" / "voice.toml").write_text('talk = "eyebrows"\n')
    bank = VoiceBank(library / "voices", Player())
    assert [v.name for v in bank.voices] == ["boss_a"]


def test_pick_weights_and_no_immediate_repeat(library):
    bank = VoiceBank(library / "voices", Player(), rng=random.Random(1))
    names = [bank.pick("awaken").voice.name for _ in range(400)]
    assert 0.65 < names.count("boss_a") / len(names) < 0.85  # weight 3 vs 1
    bank.only = "boss_a"
    paths = [bank.pick("awaken").path.name for _ in range(20)]
    assert all(a != b for a, b in zip(paths, paths[1:]))
    assert bank.pick("outro") is None


def test_speak_chance_and_no_talking_over_itself(library):
    player = Player()
    bank = VoiceBank(library / "voices", player, chance={"awaken": 0.0, "scream": 1.0})
    assert bank.speak("awaken", now=0) is None
    line = bank.speak("scream", now=0)
    assert line is not None and line.duration == pytest.approx(2.0, abs=0.01)
    assert bank.speak("scream", now=1.0) is None  # still talking
    assert bank.speak("awaken", now=2.5, force=True) is not None
    assert len(player.played) == 2


def test_talking_scene_follows_envelope(library, tmp_path):
    bank = VoiceBank(library / "voices", Player())
    bank.only = "boss_a"
    line = bank.pick("awaken")
    line.info.envelope[:] = 0
    line.info.envelope[10:20] = 1.0
    scene = scenes.talking(line, "awake")
    lay = Layout(Config().leds)
    quiet = scene.render(0.05, lay)
    loud = scene.render(0.3, lay)
    assert loud[lay.pupils.index].max() > 3 * quiet[lay.pupils.index].max()


def test_talk_effect_after_clip_sits_at_floor():
    lay = Layout(Config().leds)
    eff = Talk(Solid("white"), np.ones(5), rate=50, floor=0.2)
    assert eff.render(0.0, lay.pupils).max() == pytest.approx(1.0)
    assert eff.render(5.0, lay.pupils).max() == pytest.approx(0.2)


def test_library_report_flags_problems(library):
    cfg = Config()
    cfg.audio.folder = str(library)
    (library / "voices" / "boss_b" / "voice.toml").write_text('scene = "nope"\n')
    (library / "voices" / "boss_b" / "screams").mkdir()
    audio.write_wav(library / "countdown" / "long.wav", np.full(8000 * 5, 0.001), 8000)
    rows = library_report(cfg)
    notes = {(r[0], r[1], r[2]): r[4] + r[5] for r in rows}
    assert any("unknown scene" in n for n in notes[("boss_b", "-", "voice.toml")])
    assert any("unknown event folder" in n for n in notes[("boss_b", "screams", "")])
    long_notes = notes[("sfx", "countdown", "long.wav")]
    assert "quiet" in long_notes and any("countdown" in n for n in long_notes)
    assert notes[("boss_a", "awaken", "hello.wav")] == []


def test_real_library_is_clean():
    """Checks whatever is in sounds/ right now (skips when it's empty)."""
    rows = library_report(Config())
    if not rows:
        pytest.skip("no clips in sounds/ yet")
    problems = [(r[0], r[1], r[2], r[4]) for r in rows if r[4]]
    assert not problems

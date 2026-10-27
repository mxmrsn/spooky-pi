import numpy as np
import pytest

from spooky.config import HandpieceConfig
from spooky.handpiece import LOOKS, Handpiece, parse
from spooky.hw.teensy import HANDPIECE, encode_frame


class Strip:
    def __init__(self):
        self.frames = []

    def write(self, rgb):
        self.frames.append(rgb.copy())

    def close(self):
        pass


@pytest.fixture
def hand():
    return Handpiece(HandpieceConfig(brightness=1.0, max_current_a=100), 1.0, Strip())


def test_handpiece_frames_go_on_their_own_channel():
    assert encode_frame(np.ones((8, 3), np.uint8), HANDPIECE)[:3] == b"\xa5\x5b\x08"


def test_parse_looks_and_colours():
    assert parse("strobe") == ("strobe", None) and parse("pulse:#00ff00") == ("pulse", "#00ff00")
    assert parse("glow:toxic") == ("glow", "toxic")
    for bad in ("disco", "pulse:#zz0000", "pulse:purple"):
        with pytest.raises(ValueError):
            parse(bad)


@pytest.mark.parametrize("look", list(LOOKS))
def test_every_look_renders_eight_leds(hand, look):
    hand.hold(look, None, 0.0)
    for t in (0.0, 0.3, 1.7):
        hand.render(t)
    frame = hand.strip.frames[-1]
    assert frame.shape == (8, 3) and frame.dtype == np.uint8


def test_state_look_then_a_timed_hold(hand):
    hand.set_state("REVEAL", 10.0)
    assert hand.status(10.0) == {"look": "strobe", "held": False, "seconds_left": None}
    hand.hold("solid", "#00ff00", 10.0, seconds=2)
    hand.render(10.5)
    assert hand.strip.frames[-1][0].tolist() == [0, 255, 0]
    assert hand.status(11.0)["seconds_left"] == pytest.approx(1.0)
    hand.render(12.5)  # hold over: back to the state's look
    assert hand.status(12.5)["look"] == "strobe" and not hand.status(12.5)["held"]


def test_current_cap_dims_it():
    capped = Handpiece(HandpieceConfig(brightness=1.0, max_current_a=0.1), 1.0, Strip())
    capped.hold("solid", "white", 0.0)
    capped.render(0.1)
    assert capped.strip.frames[-1].max() < 80  # 8 white LEDs want ~0.5 A

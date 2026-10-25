import numpy as np
import pytest

from spooky import scenes
from spooky.config import LedConfig
from spooky.hw.leds import BIT0, BIT1, RESET_BYTES, encode
from spooky.layout import Layout


PUPILS = [["left_ring", 16], ["left_pupil", 1], ["right_ring", 16], ["right_pupil", 1]]


def test_chain_order_with_pupils():
    lay = Layout(LedConfig(chain=PUPILS))
    # left ring, left pupil, right ring, right pupil along the wire
    assert list(lay.perm) == list(range(16)) + [32] + list(range(16, 32)) + [33]


def test_ring_offset_and_direction():
    cfg = LedConfig(chain=PUPILS, ring_offset=[4, 0], ring_clockwise=[True, False])
    lay = Layout(cfg)
    assert lay.perm[4] == 0  # physical pixel 4 of the left ring sits at 12 o'clock
    assert lay.perm[5] == 1  # and the index runs clockwise
    right = lay.perm[17:33] - 16
    assert right[0] == 0 and right[1] == 15  # anticlockwise wiring on the right ring


def test_default_chain_has_no_pupils():
    lay = Layout(LedConfig())
    assert lay.n == lay.n_physical == 32 and lay.pupils.n == 0 and list(lay.perm) == list(range(32))
    frame = scenes.make("idle").render(1.0, lay)  # the pupils effect has nothing to draw
    assert frame.shape == (32, 3) and lay.to_physical(frame).shape == (32, 3)


def test_bad_chain_rejected():
    for chain in ([["left_ring", 16], ["right_ring", 16], ["left_pupil", 1], ["left_pupil", 1]],
                  [["left_ring", 16], ["left_ring", 16]],
                  [["left_ring", 16], ["right_ring", 16], ["nose", 1]]):
        with pytest.raises(ValueError):
            Layout(LedConfig(chain=chain))


def test_mirrored_angle_is_symmetric_about_nose():
    lay = Layout(LedConfig())
    px = lay.rings
    left = px.mangle[px.eye == 0]
    right = px.mangle[px.eye == 1]
    left_x = px.x[px.eye == 0]
    right_x = px.x[px.eye == 1]
    for a, x in zip(left, left_x):
        j = np.argmin(np.abs(right - a))
        assert right_x[j] == pytest.approx(-x)


def test_brightness_gamma_and_current_cap():
    cfg = LedConfig(brightness=1.0, gamma=1.0, max_current_a=0.5)
    lay = Layout(cfg)
    phys = lay.to_physical(np.ones((lay.n, 3)))
    assert lay.estimate_current_a(phys) <= 0.5 + 0.01
    half = Layout(LedConfig(brightness=0.5, gamma=2.0, max_current_a=100)).to_physical(np.full((32, 3), 0.5))
    assert half.max() == round(255 * 0.25 * 0.5)


def test_spi_encoding():
    phys = np.zeros((2, 3), np.uint8)
    phys[0] = (255, 0, 0)  # red -> GRB: G=0, R=255, B=0
    data = encode(phys)
    assert len(data) == 1 + 2 * 24 + RESET_BYTES
    px0 = data[1:25]
    assert set(px0[:8]) == {BIT0} and set(px0[8:16]) == {BIT1} and set(px0[16:24]) == {BIT0}
    assert data[-RESET_BYTES:] == bytes(RESET_BYTES)


@pytest.mark.parametrize("name", list(scenes.SCENES))
def test_every_scene_renders_valid_frames(name):
    lay = Layout(LedConfig())
    scene = scenes.make(name)
    for t in np.linspace(0, 10, 37):
        frame = scene.render(float(t), lay)
        assert frame.shape == (lay.n, 3)
        assert np.isfinite(frame).all()
        assert frame.min() >= 0 and frame.max() <= 1


def test_gaze_points_where_asked():
    lay = Layout(LedConfig())
    scene = scenes.make("watching")
    scene.gaze.look = (1.0, 0.0)  # look right, seen from the front
    scene.gaze.glide = 0
    frame = scene.render(0.0, lay)
    ring = frame[lay.rings.index].sum(1)
    brightest = lay.rings.angle[np.argmax(ring[:16])]
    assert brightest == pytest.approx(0.25)  # 3 o'clock

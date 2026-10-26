import http.client
import time
import urllib.error
import urllib.request

import cv2
import numpy as np
import pytest

from spooky.config import DisplayConfig
from spooky.hw.display import WebDisplay, idle_card
from spooky.web import WebServer


@pytest.fixture
def display(tmp_path):
    cfg = DisplayConfig(file_path=str(tmp_path / "display.jpg"), size=[640, 360])
    d = WebDisplay(cfg, tmp_path)
    d.KEEPALIVE = 0.2
    web = WebServer(0, display=d, host="127.0.0.1")
    d.port = web.port
    yield d
    web.close()
    d.close()


def read_frame(resp):
    """Read one multipart JPEG frame from an MJPEG response."""
    assert resp.readline().strip() == b"--spookyframe"
    headers = {}
    while (line := resp.readline().strip()):
        k, v = line.decode().split(":", 1)
        headers[k.lower()] = v.strip()
    assert headers["content-type"] == "image/jpeg"
    jpg = resp.read(int(headers["content-length"]))
    resp.readline()
    return cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)


def test_stream_sends_current_picture_then_updates(display):
    port = display.port
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/stream.mjpg")
    resp = conn.getresponse()
    assert resp.status == 200 and "multipart/x-mixed-replace" in resp.getheader("Content-Type")

    first = read_frame(resp)  # the idle card, straight away
    assert first.shape == (360, 640, 3)

    red = np.zeros((100, 100, 3), np.uint8)
    red[:] = (0, 0, 255)
    t0 = time.monotonic()
    display.show(red)
    frame = read_frame(resp)
    assert time.monotonic() - t0 < 1.0
    assert frame[180, 320, 2] > 200 and frame[180, 320, 0] < 60  # centre is red (letterboxed square)
    assert frame[180, 10].max() < 30  # black bars at the sides

    again = read_frame(resp)  # keepalive repeat of the same picture
    assert np.abs(again.astype(int) - frame.astype(int)).mean() < 2
    conn.close()


def test_snapshot_viewer_and_file(display, tmp_path):
    port = display.port
    display.show(idle_card((640, 360), "HOLD STILL!"))
    jpg = urllib.request.urlopen(f"http://127.0.0.1:{port}/frame.jpg").read()
    assert cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR).shape == (360, 640, 3)
    assert b"/stream.mjpg" in urllib.request.urlopen(f"http://127.0.0.1:{port}/").read()
    assert b"POST /api/imx" in urllib.request.urlopen(f"http://127.0.0.1:{port}/api").read()
    with pytest.raises(urllib.error.HTTPError) as e:  # no show on this server, so no control API
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/eyes")
    assert e.value.code == 503
    assert (tmp_path / "display.jpg").read_bytes() == jpg  # the Studio preview file matches the stream


class Watcher:
    def __init__(self):
        from spooky.hw.camera import Sighting
        frame = np.zeros((720, 1280, 3), np.uint8)
        faces = np.array([[640, 200, 200, 200] + [0] * 10 + [0.93]], np.float32)
        self.sighting, self.enabled, self.fps = Sighting(0.0, frame, faces), True, 12.0

    def latest(self):
        return self.sighting


def test_camera_preview_boxes_faces(display):
    port = display.port
    off = cv2.imdecode(np.frombuffer(display.camera_jpg(), np.uint8), cv2.IMREAD_COLOR)
    assert off.shape == (360, 640, 3)  # "no camera" card
    display.watcher = Watcher()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/camera.mjpg")
    img = read_frame(conn.getresponse())
    conn.close()
    assert img.shape == (360, 640, 3)
    assert img[100:200, 320:420, 1].max() > 150  # the green face box, scaled to the preview
    assert b"/camera.mjpg" in urllib.request.urlopen(f"http://127.0.0.1:{port}/camera").read()
    display.watcher.enabled = False
    assert np.array_equal(cv2.imdecode(np.frombuffer(display.camera_jpg(), np.uint8), cv2.IMREAD_COLOR).shape,
                          (360, 640, 3))


def test_live_feed_then_stills(display):
    display.LIVE_FPS = 50
    display.watcher = Watcher()
    display.feed("Step closer", "3")
    time.sleep(0.15)
    img = cv2.imdecode(np.frombuffer(display.jpg, np.uint8), cv2.IMREAD_COLOR)
    assert img.shape == (360, 640, 3) and img[150:210, 290:350].max() > 200  # the big white "3"
    photo = np.full((300, 200, 3), 80, np.uint8)
    display.compare(photo, photo + 100)
    assert display.live is None
    v = display.version
    time.sleep(0.1)
    assert display.version == v  # the live loop leaves the still alone
    img = cv2.imdecode(np.frombuffer(display.jpg, np.uint8), cv2.IMREAD_COLOR)
    assert abs(int(img[180, 200, 0]) - 80) < 15 and abs(int(img[180, 440, 0]) - 180) < 15  # before | after


def test_live_feed_keeps_flowing_while_prompts_update_every_tick(display):
    """The show calls feed() every 20 ms; frames must still get through."""
    display.LIVE_FPS = 50
    display.watcher = Watcher()
    v = display.version
    end = time.monotonic() + 0.5
    while time.monotonic() < end:
        display.feed("Step closer... if you dare")
        time.sleep(0.005)
    assert display.version - v >= 5

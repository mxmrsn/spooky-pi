import http.client
import time
import urllib.request

import cv2
import numpy as np
import pytest

from spooky.config import DisplayConfig
from spooky.hw.display import StreamDisplay, idle_card


@pytest.fixture
def display(tmp_path):
    cfg = DisplayConfig(stream_port=0, file_path=str(tmp_path / "display.jpg"), size=[640, 360])
    d = StreamDisplay(cfg, tmp_path, host="127.0.0.1")
    d.KEEPALIVE = 0.2
    yield d
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
    port = display.server.server_address[1]
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
    port = display.server.server_address[1]
    display.show(idle_card((640, 360), "HOLD STILL!"))
    jpg = urllib.request.urlopen(f"http://127.0.0.1:{port}/frame.jpg").read()
    assert cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR).shape == (360, 640, 3)
    assert b"/stream.mjpg" in urllib.request.urlopen(f"http://127.0.0.1:{port}/").read()
    assert (tmp_path / "display.jpg").read_bytes() == jpg  # the Studio preview file matches the stream

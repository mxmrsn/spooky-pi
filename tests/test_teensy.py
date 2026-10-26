import numpy as np
import pytest

from spooky.hw import teensy
from spooky.hw.teensy import KEEPALIVE, RETRY, TeensyLink, encode_frame


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakeSerial:
    """Stands in for serial.Serial: records writes, serves queued reads."""

    def __init__(self):
        self.written = bytearray()
        self.incoming = bytearray()
        self.fail = False
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.incoming)

    def read(self, n):
        if self.fail:
            raise OSError("device vanished")
        out, self.incoming = bytes(self.incoming[:n]), self.incoming[n:]
        return out

    def write(self, data):
        if self.fail:
            raise OSError("device vanished")
        self.written += data

    def close(self):
        self.closed = True


@pytest.fixture
def rig():
    clock, ports = Clock(), []

    def opener(port):
        if ports and ports[-1] is None:
            raise OSError("no Teensy")
        ports.append(FakeSerial())
        return ports[-1]

    link = TeensyLink(opener=opener, clock=clock, start=False)
    return link, ports, clock


def test_frame_encoding():
    rgb = np.array([[1, 2, 3], [250, 250, 250]], np.uint8)
    frame = encode_frame(rgb)
    assert frame[:3] == b"\xa5\x5a\x02"
    assert frame[3:9] == bytes([1, 2, 3, 250, 250, 250])
    assert frame[9] == (6 + 750) & 0xFF and len(frame) == 10
    assert encode_frame(np.zeros((0, 3), np.uint8)) == b"\xa5\x5a\x00\x00"
    with pytest.raises(ValueError):
        encode_frame(np.zeros((256, 3), np.uint8))


def test_asks_for_hello_and_sends_frames(rig):
    link, ports, clock = rig
    assert ports[0].written == b"?"
    link.send_leds(np.full((34, 3), 7, np.uint8))
    assert ports[0].written[1:] == encode_frame(np.full((34, 3), 7, np.uint8))


def test_reads_the_hello_line_split_across_reads(rig):
    link, ports, clock = rig
    ports[0].incoming += b"S 00\nspooky-teensy 3 leds=64 fr"  # old firmware's status lines are ignored
    link.step()
    ports[0].incoming += b"ames=0 bad=0\n"
    link.step()
    assert link.hello == "spooky-teensy 3 leds=64 frames=0 bad=0" and not link.warned


def test_keepalive_resends_last_frame(rig):
    link, ports, clock = rig
    link.step()  # nothing to keep alive yet
    assert ports[0].written == b"?"
    link.send_leds(np.ones((2, 3), np.uint8))
    sent = len(ports[0].written)
    clock.t += KEEPALIVE / 2
    link.step()
    assert len(ports[0].written) == sent
    clock.t += KEEPALIVE
    link.step()
    assert len(ports[0].written) == 2 * sent - 1


def test_reconnects_and_resends_after_unplug(rig):
    link, ports, clock = rig
    ports[0].fail = True
    link.send_leds(np.ones((2, 3), np.uint8))  # write fails: the link drops
    assert link.ser is None and ports[0].closed
    link.send_leds(np.ones((2, 3), np.uint8))  # no port: ignored
    ports.append(None)
    clock.t += RETRY
    link.step()  # still unplugged
    assert link.ser is None
    ports.pop()
    clock.t += RETRY
    link.step()
    assert link.ser is ports[1] and ports[1].written == b"?" + encode_frame(np.ones((2, 3), np.uint8))


def test_warns_once_about_foreign_firmware(rig, caplog):
    link, ports, clock = rig
    ports[0].incoming += b"status: eth=DOWN\nstatus: eth=DOWN\n"
    link.step()
    assert sum("spooky firmware" in r.message for r in caplog.records) == 1


def test_shared_link_closes_with_last_user(monkeypatch):
    opened = []

    class Link(TeensyLink):
        def __init__(self, port=""):
            super().__init__(port, opener=lambda p: opened.append(FakeSerial()) or opened[-1], start=False)

    monkeypatch.setattr(teensy, "TeensyLink", Link)
    a, b = teensy.TeensyStrip(), teensy.TeensyStrip()
    assert a.link is b.link and len(opened) == 1
    a.close()
    assert not opened[0].closed
    b.close()
    assert opened[0].closed and teensy._links == {}

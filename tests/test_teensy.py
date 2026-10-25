import numpy as np
import pytest

from spooky.hw import teensy
from spooky.hw.inputs import PirMonitor, PirSensors
from spooky.hw.teensy import KEEPALIVE, RETRY, TeensyInput, TeensyLink, encode_frame


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


def test_pir_levels_drive_inputs(rig):
    link, ports, clock = rig
    a, b = TeensyInput(0, link=link), TeensyInput(1, link=link)
    sensors = PirSensors([a, b])
    ports[0].incoming += b"spooky-teensy 1 leds=64 pirs=2\nS 00\nS 0"
    link.step()
    assert link.hello.startswith("spooky-teensy") and sensors.poll() == [] and not sensors.active()
    ports[0].incoming += b"1\n"  # a line split across reads
    link.step()
    assert (a.value, b.value) == (0, 1) and sensors.poll() == [1] and sensors.active()
    ports[0].incoming += b"S 11\nS 11\n"
    link.step()
    assert sensors.poll() == [0]  # one event per rising edge, not per report


def test_monitor_traces_teensy_inputs(rig):
    link, ports, clock = rig
    mon = PirMonitor([2, 3], devices=[TeensyInput(i, link=link) for i in range(2)], clock=clock)
    ports[0].incoming += b"S 10\n"
    link.step()
    clock.t += 1.0
    mon.sample()
    snap = mon.snapshot()
    assert snap["pins"] == [2, 3] and snap["levels"] == [1, 0] and snap["stats"][0]["pulses"] == 1


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
    inp = TeensyInput(0, link=link)
    ports[0].incoming += b"S 1\n"
    link.step()
    assert inp.value == 1
    ports[0].fail = True
    link.send_leds(np.ones((2, 3), np.uint8))  # write fails: link drops, PIRs read quiet
    assert link.ser is None and ports[0].closed and inp.value == 0
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
    strip = teensy.TeensyStrip()
    inp = TeensyInput(0)
    assert inp.link is strip.link and len(opened) == 1
    strip.close()
    assert not opened[0].closed
    inp.close()
    assert opened[0].closed and teensy._links == {}

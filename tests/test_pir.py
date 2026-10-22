import pytest

from spooky.hw.inputs import MonitorInputs, PirMonitor


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakePin:
    """Stands in for gpiozero.DigitalInputDevice."""

    def __init__(self):
        self.value = 0
        self.when_activated = self.when_deactivated = None

    def set(self, v):
        self.value = v
        (self.when_activated if v else self.when_deactivated)()

    def close(self):
        pass


@pytest.fixture
def mon():
    clock = Clock()
    pins = [FakePin(), FakePin()]
    return PirMonitor([23, 24], devices=pins, clock=clock), pins, clock


def test_pulse_stats_and_trace(mon):
    m, pins, clock = mon
    for _ in range(10):
        clock.t += 0.1
        m.sample()
    pins[0].set(1)
    clock.t += 2.5
    m.sample()
    snap = m.snapshot()
    assert snap["levels"] == [1, 0] and snap["stats"][0]["high_now"] == pytest.approx(2.5)
    pins[0].set(0)
    clock.t += 0.5
    m.sample()
    snap = m.snapshot()
    st = snap["stats"][0]
    assert st["pulses"] == 1 and st["last_high"] == pytest.approx(2.5) and st["high_now"] == 0
    assert snap["stats"][1]["pulses"] == 0
    assert snap["trace"][-1] == [0.0, 0, 0] and all(t <= 0 for t, *_ in snap["trace"])

    clock.t += m.WINDOW + 1  # old samples fall out of the window
    m.sample()
    assert len(m.snapshot()["trace"]) == 1
    m.reset_stats()
    assert m.snapshot()["stats"][0]["pulses"] == 0


def test_monitor_inputs_feed_the_show(mon):
    m, pins, clock = mon
    pins[1].set(1)  # before the show starts: ignored
    pins[1].set(0)
    inputs = MonitorInputs(m)
    assert inputs.poll() == [] and not inputs.active()
    pins[0].set(1)
    assert inputs.poll() == [0] and inputs.active()
    pins[0].set(0)
    inputs.trigger(1)  # the Studio's "someone walks up" button still works
    assert inputs.poll() == [1] and inputs.active()

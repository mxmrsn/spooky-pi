import pytest


class FakeClock:
    """A monotonic clock that only moves when a test sets or advances `t`."""

    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return FakeClock()

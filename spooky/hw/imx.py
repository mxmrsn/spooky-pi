"""Animation triggers for the i.MX 8M Plus, which plays its own animations on its own display.

The show sends one UDP datagram per trigger to [imx] host:port, a JSON object:

    {"cmd": "play", "animation": "awake", "state": "AWAKE", "seq": 12}

`state` is the show state that caused it (null for a manual trigger through the control
API) and `seq` counts up from 1 each time the show starts. Fire and forget: nothing comes
back, and a missing i.MX never slows the show down. Receiver: imx/spooky-trigger.py.
"""

import json
import logging
import socket
import threading

log = logging.getLogger(__name__)


class ImxLink:
    def __init__(self, host, port):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.seq = 0
        self.lock = threading.Lock()
        self.failing = False

    def play(self, animation, state=None):
        with self.lock:
            self.seq += 1
            msg = {"cmd": "play", "animation": animation, "state": state, "seq": self.seq}
        try:
            self.sock.sendto(json.dumps(msg).encode(), self.addr)
            if self.failing:
                log.info("i.MX reachable again")
            self.failing = False
            log.info("i.MX <- %s", animation)
        except OSError as e:  # e.g. no Ethernet cable: say so once, keep the show going
            if not self.failing:
                log.warning("can't send to the i.MX at %s:%d (%s)", *self.addr, e)
            self.failing = True

    def close(self):
        self.sock.close()


class LogImx:
    """Stand-in that only logs, for --sim."""

    def play(self, animation, state=None):
        log.info("i.MX <- %s (simulated)", animation)

    def close(self):
        pass

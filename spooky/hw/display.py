"""Photo display. The real display's interface isn't settled yet, so this is pluggable:

    pygame  fullscreen on the Pi's desktop (HDMI or any screen the desktop drives)
    file    writes what would be shown to a JPEG (simulation / headless)
    none    discards everything

All take BGR numpy images (OpenCV's format).
"""

import logging
import os
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

ROTATE = {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def fit(img, size):
    """Letterbox a BGR image into size (w, h) on black."""
    w, h = size
    ih, iw = img.shape[:2]
    k = min(w / iw, h / ih)
    nw, nh = max(1, round(iw * k)), max(1, round(ih * k))
    out = np.zeros((h, w, 3), np.uint8)
    x, y = (w - nw) // 2, (h - nh) // 2
    out[y:y + nh, x:x + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    return out


def idle_card(size, text="Step closer... if you dare"):
    w, h = size
    out = np.zeros((h, w, 3), np.uint8)
    scale = w / 900
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, scale, 2)
    cv2.putText(out, text, ((w - tw) // 2, (h + th) // 2), cv2.FONT_HERSHEY_DUPLEX, scale,
                (0, 0, 160), max(1, round(2 * scale)), cv2.LINE_AA)
    return out


class _Base:
    def __init__(self, cfg, root):
        self.rotate = ROTATE[cfg.rotate % 360]
        p = root / cfg.idle_image
        self.idle_image = cv2.imread(str(p)) if p.is_file() else None

    def _prep(self, img):
        return cv2.rotate(img, self.rotate) if self.rotate is not None else img

    def idle(self):
        self.show(self.idle_image if self.idle_image is not None else idle_card(self.native_size()))

    def pump(self):
        """Handle window events; returns False if the user asked to quit."""
        return True

    def close(self):
        pass


class PygameDisplay(_Base):
    def __init__(self, cfg, root):
        super().__init__(cfg, root)
        # When started over SSH, borrow the logged-in desktop session
        runtime = f"/run/user/{os.getuid()}"
        os.environ.setdefault("XDG_RUNTIME_DIR", runtime)
        if "WAYLAND_DISPLAY" not in os.environ and Path(runtime, "wayland-0").exists():
            os.environ["WAYLAND_DISPLAY"] = "wayland-0"
        import pygame
        pygame.display.init()
        self.pygame = pygame
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("spooky-pi")
        pygame.mouse.set_visible(False)
        log.info("display %dx%d", *self.screen.get_size())

    def native_size(self):
        w, h = self.screen.get_size()
        return (h, w) if self.rotate in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE) else (w, h)

    def show(self, img):
        img = self._prep(fit(img, self.native_size()))
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        surf = self.pygame.image.frombuffer(rgb.tobytes(), (rgb.shape[1], rgb.shape[0]), "RGB")
        self.screen.blit(surf, (0, 0))
        self.pygame.display.flip()

    def pump(self):
        for e in self.pygame.event.get():
            if e.type == self.pygame.QUIT or (e.type == self.pygame.KEYDOWN and e.key == self.pygame.K_ESCAPE):
                return False
        return True

    def close(self):
        self.pygame.display.quit()


class FileDisplay(_Base):
    SIZE = (1080, 1920)  # portrait, matching the rotated camera

    def __init__(self, cfg, root):
        super().__init__(cfg, root)
        self.path = root / cfg.file_path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def native_size(self):
        return self.SIZE

    def show(self, img):
        tmp = self.path.with_suffix(".tmp.jpg")
        cv2.imwrite(str(tmp), self._prep(fit(img, self.SIZE)))
        os.replace(tmp, self.path)
        log.info("display -> %s", self.path.name)


class NullDisplay(_Base):
    def __init__(self, cfg=None, root=None):
        self.rotate, self.idle_image = None, None

    def native_size(self):
        return (1080, 1920)

    def show(self, img):
        pass

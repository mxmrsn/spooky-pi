"""Render every LED scene to an image (docs/img/scenes.png) for the README.

Each row is a scene, each column a moment in time, drawn from the same code that
drives the real glasses. Rerun after changing scenes.py:

    python tools/render_scenes.py
"""

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from spooky import config, scenes  # noqa: E402
from spooky.layout import Layout  # noqa: E402

TIMES = (0.0, 0.4, 0.8, 1.2, 1.6, 2.0)
CELL_W, CELL_H, R, LED = 230, 110, 40, 7
LABEL_W = 170
BG = (24, 18, 18)


def draw_glasses(img, ox, oy, frame, layout):
    px = layout.all
    for i in np.argsort(-frame.sum(1)):  # dim first so bright glows sit on top
        cx = ox + CELL_W / 2 + px.x[i] * (R + 4)
        cy = oy + CELL_H / 2 - px.y[i] * R
        b, g, r = (frame[i][::-1] * 255).astype(int).tolist()
        c = (int(cx), int(cy))
        if max(r, g, b) > 30:  # soft glow
            glow = img.copy()
            cv2.circle(glow, c, LED * 2, (b, g, r), -1, cv2.LINE_AA)
            cv2.addWeighted(glow, 0.25, img, 0.75, 0, img)
        cv2.circle(img, c, LED, (max(b, 40), max(g, 40), max(r, 40)) if max(r, g, b) < 40 else (b, g, r), -1,
                   cv2.LINE_AA)
    for side in (-1, 1):  # frames of the glasses
        cv2.circle(img, (int(ox + CELL_W / 2 + side * 1.25 * (R + 4)), int(oy + CELL_H / 2)), R + 12,
                   (70, 60, 60), 1, cv2.LINE_AA)


def main():
    cfg = config.load()
    layout = Layout(cfg.leds)
    state_of = {v: k for k, v in scenes.STATE_SCENES.items()}
    names = list(scenes.STATE_SCENES.values()) + [n for n in scenes.SCENES
                                                    if n not in scenes.STATE_SCENES.values() and n != "off"]
    h = 40 + CELL_H * len(names)
    img = np.full((h, LABEL_W + CELL_W * len(TIMES), 3), BG, np.uint8)
    for j, t in enumerate(TIMES):
        cv2.putText(img, f"t = {t:.1f} s", (LABEL_W + j * CELL_W + 75, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (160, 160, 160), 1, cv2.LINE_AA)
    for i, name in enumerate(names):
        y = 40 + i * CELL_H
        scene = scenes.make(name)
        if scene.gaze is not None:
            scene.gaze.glide = 0
        label = name if name not in state_of else f"{name}"
        cv2.putText(img, label, (12, y + CELL_H // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1, cv2.LINE_AA)
        if name in state_of:
            cv2.putText(img, state_of[name], (12, y + CELL_H // 2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                        (120, 120, 200), 1, cv2.LINE_AA)
        for j, t in enumerate(TIMES):
            if scene.gaze is not None:  # show the eyes sweeping as if following someone
                scene.gaze.look = (np.sin(t * 1.6) * 0.9, -0.4)
            draw_glasses(img, LABEL_W + j * CELL_W, y, scene.render(t, layout), layout)
        cv2.line(img, (0, y + CELL_H - 1), (img.shape[1], y + CELL_H - 1), (40, 34, 34), 1)
    out = cfg.path("docs/img/scenes.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)
    print(f"Wrote {out} ({len(names)} scenes)")


if __name__ == "__main__":
    main()

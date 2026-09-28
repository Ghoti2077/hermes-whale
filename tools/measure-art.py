"""Measure two things on the whale art:

1. the thought bubble's real bounding box (white blob in the upper half) —
   hard-coded fractions in BUBBLE drifted the text outside the bubble
2. the pale "window frame" tile texture behind the girl — so it can be masked out

Read-only. Run:  python tools/measure-art.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ART = Path(r"D:\APP\herness\profiles\web\node_modules\dsh-whale-widget\assets\DSniang02.png")


def main() -> int:
    im = Image.open(ART).convert("RGBA")
    w, h = im.size
    px = im.load()
    print(f"size: {w}x{h}")

    # --- 1. white bubble in the upper half, inside the opaque region
    min_x, min_y, max_x, max_y = w, h, -1, -1
    for y in range(0, int(h * 0.55)):
        for x in range(0, w):
            r, g, b, a = px[x, y]
            if a < 200:
                continue
            if r > 235 and g > 235 and b > 235:
                min_x = min(min_x, x); max_x = max(max_x, x)
                min_y = min(min_y, y); max_y = max(max_y, y)
    if max_x > 0:
        print("bubble bbox px:", (min_x, min_y, max_x, max_y))
        print("bubble frac   : x=%.4f y=%.4f w=%.4f h=%.4f"
              % (min_x / w, min_y / h, (max_x - min_x) / w, (max_y - min_y) / h))
        print("bubble centre : %.4f, %.4f"
              % ((min_x + max_x) / 2 / w, (min_y + max_y) / 2 / h))
    else:
        print("bubble: not found")

    # --- 2. pale tile texture: light, low-saturation pixels in the lower half
    tiles = 0
    lower = 0
    for y in range(int(h * 0.55), h):
        for x in range(0, w):
            r, g, b, a = px[x, y]
            if a < 200:
                continue
            lower += 1
            mx, mn = max(r, g, b), min(r, g, b)
            # light grey/white: bright and nearly neutral
            if mn > 185 and (mx - mn) < 22:
                tiles += 1
    print(f"lower-half opaque px: {lower}, pale-grey px: {tiles} "
          f"({100 * tiles / max(1, lower):.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

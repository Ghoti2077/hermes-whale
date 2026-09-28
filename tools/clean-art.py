"""Mask out the pale 'window frame' tile texture behind the whale girl.

A colour threshold cannot do this: the tiles are nearly as white as her apron.
What DOES separate them is connectivity — the girl and her thought bubble form
one or two big solid blobs, while the tile pattern is a scatter of smaller
fragments around them.

So: label the opaque mask, keep the biggest N blobs, clear the rest.

Run:  python tools/clean-art.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

SRC = Path(r"D:\APP\herness\profiles\web\node_modules\dsh-whale-widget\assets\DSniang02.png")
OUT = Path(__file__).resolve().parents[1] / "art" / "whale.png"

ALPHA_MIN = 128      # below this counts as background
KEEP_TOP = 3         # biggest blobs to keep (girl+bubble, plus the little bubble dots)


def main() -> int:
    im = Image.open(SRC).convert("RGBA")
    a = np.array(im)
    mask = a[:, :, 3] >= ALPHA_MIN

    labels, n = ndimage.label(mask)          # 4-connectivity
    if n == 0:
        print("no opaque region found")
        return 1

    sizes = ndimage.sum(mask, labels, range(1, n + 1))
    order = np.argsort(sizes)[::-1]          # biggest first

    print(f"components: {n}")
    print("top sizes:", [int(sizes[i]) for i in order[:8]])
    print("tail sizes:", [int(sizes[i]) for i in order[-5:]])

    keep_ids = [int(order[i]) + 1 for i in range(min(KEEP_TOP, n))]   # labels are 1-based
    keep = np.isin(labels, keep_ids)
    removed = int(mask.sum() - keep.sum())

    a[:, :, 3] = np.where(keep, a[:, :, 3], 0)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a, "RGBA").save(OUT)

    print(f"kept {len(keep_ids)} blobs (labels {keep_ids}), cleared {removed} px")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

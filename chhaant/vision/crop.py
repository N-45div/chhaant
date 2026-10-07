"""The model's view of an item: a square crop with the backdrop greyed out.

Training data comes from very different scenes (a white table, a conveyor
belt, field photos). Greying out everything outside the item's mask makes the
model look at the produce rather than learn backgrounds, which is what lets a
model trained elsewhere transfer to a new inspection cell. Training and
inference must both use this function so they see identical inputs.
"""

import cv2
import numpy as np

MODEL_SIDE = 224
MARGIN = 0.12        # space around the item's bounding box, as a share of its size
NEUTRAL = (127, 127, 127)
RIM_FRAC = 0.015     # keep a thin rim (share of the item's size) so the outline is not clipped


def item_crop(bgr: np.ndarray, mask: np.ndarray | None = None, side: int = MODEL_SIDE) -> np.ndarray:
    """Square ``side`` x ``side`` BGR crop centred on the item.

    With a mask, pixels outside the (slightly dilated) item are set to neutral
    grey. Without one, the whole image is letterboxed onto grey.
    """
    h, w = bgr.shape[:2]
    if mask is None or not np.any(mask):
        cx, cy, half = w / 2, h / 2, max(w, h) / 2
        work = bgr
    else:
        x, y, bw, bh = cv2.boundingRect(mask)
        r = max(1, round(RIM_FRAC * max(bw, bh)))  # proportional, so every resolution crops alike
        keep = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2)) > 0
        work = bgr.copy()
        work[~keep] = NEUTRAL
        cx, cy = x + bw / 2, y + bh / 2
        half = max(bw, bh) * (0.5 + MARGIN)

    x0, y0 = int(round(cx - half)), int(round(cy - half))
    size = max(1, int(round(2 * half)))
    pad = max(0, -x0, -y0, x0 + size - w, y0 + size - h)
    if pad:
        work = cv2.copyMakeBorder(work, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=NEUTRAL)
        x0, y0 = x0 + pad, y0 + pad
    crop = work[y0:y0 + size, x0:x0 + size]
    interp = cv2.INTER_AREA if size > side else cv2.INTER_LINEAR
    return cv2.resize(crop, (side, side), interpolation=interp)

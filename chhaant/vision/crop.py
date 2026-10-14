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
        region, keep = (0, 0, w, h), None
    else:
        x, y, bw, bh = cv2.boundingRect(mask)
        r = max(1, round(RIM_FRAC * max(bw, bh)))  # proportional, so every resolution crops alike
        cx, cy = x + bw / 2, y + bh / 2
        half = max(bw, bh) * (0.5 + MARGIN)
        # The dilated item reaches at most r pixels past its bounding box, so only that
        # neighbourhood is dilated and copied: a small share of a 12 MP camera frame.
        region = (max(0, x - r), max(0, y - r), min(w, x + bw + r), min(h, y + bh + r))
        rx0, ry0, rx1, ry1 = region
        keep = cv2.dilate(mask[ry0:ry1, rx0:rx1], cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2)) > 0

    x0, y0 = int(round(cx - half)), int(round(cy - half))
    size = max(1, int(round(2 * half)))
    # The backdrop, and anything past the frame's edge. NEUTRAL is a grey, so one value
    # fills all three channels: several times faster than broadcasting the tuple.
    crop = np.full((size, size, 3), NEUTRAL[0] if len(set(NEUTRAL)) == 1 else NEUTRAL, np.uint8)
    _paste(crop, bgr, x0, y0, region, keep)
    interp = cv2.INTER_AREA if size > side else cv2.INTER_LINEAR
    return cv2.resize(crop, (side, side), interpolation=interp)


def _paste(canvas: np.ndarray, bgr: np.ndarray, x0: int, y0: int, region, keep) -> None:
    """Copy the photo's ``region`` (x0, y0, x1, y1) onto the canvas, whose top-left corner
    sits at (x0, y0) in the photo; with ``keep``, only the pixels it marks."""
    rx0, ry0, rx1, ry1 = region
    size = canvas.shape[0]
    ix0, iy0, ix1, iy1 = max(rx0, x0), max(ry0, y0), min(rx1, x0 + size), min(ry1, y0 + size)
    if ix0 >= ix1 or iy0 >= iy1:
        return
    dst = canvas[iy0 - y0:iy1 - y0, ix0 - x0:ix1 - x0]
    src = bgr[iy0:iy1, ix0:ix1]
    if keep is None:
        dst[:] = src
    else:
        k = keep[iy0 - ry0:iy1 - ry0, ix0 - rx0:ix1 - rx0]
        np.copyto(dst, src, where=k[:, :, None])  # a masked copy, without fancy indexing's gather

"""Colour of the item in CIELAB, the basis for ripeness.

Two steps:

* ``white_balance_from_background`` uses the plain backdrop around the item as
  a neutral reference, so a tinted lamp or phone white-balance drift does not
  read as a ripeness change. When a ColorChecker is in frame, a chart-based
  correction (OpenCV 5's ``cv2.mcc`` + ``cv2.ccm``) is more accurate.
* ``colour_stats`` summarises the item's pixels: median L*, a*, b*, hue angle,
  chroma, the a*/b* ratio used in tomato maturity grading, and the fraction of
  pixels much darker than the item itself (spots, bruises, rot).
"""

import math
from dataclasses import dataclass

import cv2
import numpy as np

DARK_DROP_L = 25.0  # L* below the item's median by this much counts as a dark spot


@dataclass
class ColourStats:
    L: float          # median CIELAB lightness, 0-100
    a: float          # median a*, green (-) to red (+)
    b: float          # median b*, blue (-) to yellow (+)
    hue_deg: float    # atan2(b*, a*): ~30 red, ~70 orange-yellow, ~100 yellow, ~120 green
    chroma: float     # colour strength, hypot(a*, b*)
    a_over_b: float   # tomato maturity index (rises from green to red)
    dark_frac: float  # share of item pixels that are dark spots
    pixels: int       # item pixels measured


def lab_image(bgr: np.ndarray) -> np.ndarray:
    """sRGB (8-bit BGR) to CIELAB D65 as float32: L in 0-100, a/b in their natural range."""
    return cv2.cvtColor(bgr.astype(np.float32) / 255.0, cv2.COLOR_BGR2Lab)


def item_window(mask: np.ndarray, pad: int) -> tuple[slice, slice]:
    """Rows and columns of the item's bounding box grown by ``pad`` pixels (clipped to the frame)."""
    x, y, w, h = cv2.boundingRect(mask)
    return (slice(max(0, y - pad), min(mask.shape[0], y + h + pad)),
            slice(max(0, x - pad), min(mask.shape[1], x + w + pad)))


def _median_u8(bgr: np.ndarray, where: np.ndarray) -> np.ndarray:
    """Per-channel median of the 8-bit pixels where ``where`` is set, read off histograms.

    Equal to ``np.median(bgr[where].astype(np.float32), axis=0)`` (the mean of the two
    middle values when the count is even), without sorting millions of pixels.
    """
    out = []
    for c in range(3):
        cum = np.cumsum(cv2.calcHist([bgr], [c], where, [256], [0, 256]).ravel().astype(np.int64))
        n = int(cum[-1])
        lo, hi = np.searchsorted(cum, (n - 1) // 2 + 1), np.searchsorted(cum, n // 2 + 1)
        out.append((lo + hi) / 2)
    return np.array(out, np.float32)


def background_gains(bgr: np.ndarray, mask: np.ndarray, margin_px: int = 15) -> np.ndarray | None:
    """B, G, R gains that turn the backdrop (pixels away from the item) neutral grey,
    or None when too little backdrop is left to judge by."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * margin_px + 1, 2 * margin_px + 1))
    # The dilation reaches margin_px past the item at most: only that window can stop being backdrop.
    rows, cols = item_window(mask, margin_px)
    background = np.full(mask.shape, 255, np.uint8)
    background[rows, cols] = cv2.compare(cv2.dilate(mask[rows, cols], k), 0, cv2.CMP_EQ)  # 255 off the item
    if cv2.countNonZero(background) < 500:
        return None
    ref = _median_u8(bgr, background)
    return ref.mean() / np.maximum(ref, 1.0)


def apply_gains(bgr: np.ndarray, gains: np.ndarray | None) -> np.ndarray:
    if gains is None:
        return bgr.copy()
    return np.clip(bgr.astype(np.float32) * gains, 0, 255).astype(np.uint8)


def white_balance_from_background(bgr: np.ndarray, mask: np.ndarray, margin_px: int = 15) -> np.ndarray:
    """Scale B, G, R so the backdrop (pixels away from the item) becomes neutral grey."""
    return apply_gains(bgr, background_gains(bgr, mask, margin_px))


def colour_stats(bgr: np.ndarray, mask: np.ndarray, erode_px: int = 3) -> ColourStats:
    """Colour summary of the pixels inside ``mask`` (edge pixels are dropped first)."""
    if erode_px > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * erode_px + 1, 2 * erode_px + 1))
        mask = cv2.erode(mask, k)
    px = lab_image(bgr)[mask > 0]
    if len(px) == 0:
        raise ValueError("mask selects no pixels")
    L, a, b = (float(v) for v in np.median(px, axis=0))
    return ColourStats(
        L=L, a=a, b=b,
        hue_deg=math.degrees(math.atan2(b, a)) % 360.0,
        chroma=math.hypot(a, b),
        a_over_b=a / b if abs(b) > 1e-3 else math.copysign(math.inf, a),
        dark_frac=float(np.mean(px[:, 0] < L - DARK_DROP_L)),
        pixels=int(len(px)),
    )

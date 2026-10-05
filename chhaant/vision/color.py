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


def white_balance_from_background(bgr: np.ndarray, mask: np.ndarray, margin_px: int = 15) -> np.ndarray:
    """Scale B, G, R so the backdrop (pixels away from the item) becomes neutral grey."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * margin_px + 1, 2 * margin_px + 1))
    background = cv2.dilate(mask, k) == 0
    if background.sum() < 500:
        return bgr.copy()
    ref = np.median(bgr[background].astype(np.float32), axis=0)
    gains = ref.mean() / np.maximum(ref, 1.0)
    return np.clip(bgr.astype(np.float32) * gains, 0, 255).astype(np.uint8)


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

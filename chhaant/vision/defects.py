"""Classical per-pixel defect map: where does the item look rotten, bruised or spotted?

Two signals, both in CIELAB after backdrop white balance:

* dark-and-dull: rot, mould and blackened skin are dark AND colourless. This
  is absolute, not relative to the item's own median, so an item that blackens
  all over still scores high (a relative "darker than the item" test sees
  nothing there). A deep-red tomato is dark but strongly coloured, so it does
  not trigger.
* local spot: a morphological black-hat on L* finds patches darker than their
  surroundings (bruises, lesions, small spots) even on a light item.

The map is 0..1 per pixel. It is deliberately simple and explainable; a learned
model (OpenCV 5 DNN) is layered on top later, and this map stays as the
fallback and as the evidence painted onto the coverage sphere.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from .color import lab_image

DULL_L, DULL_L_SOFT = 38.0, 6.0      # "dark": L* below ~38
DULL_C, DULL_C_SOFT = 20.0, 5.0      # "colourless": chroma below ~20
SPOT_DROP, SPOT_SOFT = 12.0, 3.0     # "spot": at least ~12 L* darker than the neighbourhood
SPOT_KERNEL_FRAC = 0.15              # neighbourhood ~15% of the item's diameter
EDGE_ERODE_FRAC = 0.03               # ignore a thin rim where background bleeds in
MIN_BLOB_FRAC = 0.002                # blobs smaller than 0.2% of the item are noise


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _diameter(mask: np.ndarray) -> float:
    return float(np.sqrt(4.0 * np.count_nonzero(mask) / np.pi))


def inspected_region(mask: np.ndarray) -> np.ndarray:
    """The item minus a thin rim where background bleeds into edge pixels."""
    e = max(1, int(EDGE_ERODE_FRAC * max(_diameter(mask), 8.0)))
    return cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * e + 1, 2 * e + 1)))


def defect_map(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Per-pixel defect probability (float32, 0..1), zero outside the item."""
    d = max(_diameter(mask), 8.0)
    lab = lab_image(bgr)
    L, chroma = lab[..., 0], np.hypot(lab[..., 1], lab[..., 2])

    dark_dull = _sigmoid((DULL_L - L) / DULL_L_SOFT) * _sigmoid((DULL_C - chroma) / DULL_C_SOFT)

    k = max(3, int(SPOT_KERNEL_FRAC * d) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    blackhat = cv2.morphologyEx(L, cv2.MORPH_BLACKHAT, kernel)
    spot = _sigmoid((blackhat - SPOT_DROP) / SPOT_SOFT)

    prob = np.maximum(dark_dull, spot).astype(np.float32)
    prob[inspected_region(mask) == 0] = 0.0
    return prob


@dataclass
class DefectSummary:
    area_frac: float          # share of the item's pixels with defect probability > 0.5
    blobs: int                # separate defect patches
    largest_blob_frac: float  # the biggest patch, as a share of the item
    mean_prob: float          # mean probability over the item


def summarise(prob: np.ndarray, mask: np.ndarray) -> DefectSummary:
    """Summary over the inspected region (the same region ``defect_map`` scores)."""
    region = inspected_region(mask)
    item = np.count_nonzero(region)
    if item == 0:
        raise ValueError("empty mask")
    hot = ((prob > 0.5) & (region > 0)).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(hot, connectivity=8)
    areas = [stats[i, cv2.CC_STAT_AREA] for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= MIN_BLOB_FRAC * item]
    return DefectSummary(
        area_frac=float(hot.sum()) / item,
        blobs=len(areas),
        largest_blob_frac=float(max(areas, default=0)) / item,
        mean_prob=float(prob[region > 0].mean()),
    )

"""Find the fruit in a photo: a mask, its outline, and whether to trust it.

The inspection cell photographs one item on a plain, light background. The
background colour is estimated from the image border, and a pixel counts as
fruit when it differs from that colour. Colour (a*, b*) differences count in
full; brightness differences only count beyond a tolerance, so the soft grey
shadow under the fruit is ignored while a blackened, spoiled fruit is still
found.
"""

from dataclasses import dataclass

import cv2
import numpy as np

WORK_SIDE = 512          # segmentation runs at this size, then the mask is scaled back
BORDER_FRAC = 0.06       # width of the border band used to model the background
SHADOW_TOLERANCE_L = 22  # L* drop (0-100 scale) still treated as shadow, not fruit
MIN_CONTRAST = 10.0      # below this Lab distance nothing stands out: no fruit
MIN_AREA_FRAC, MAX_AREA_FRAC = 0.01, 0.85


@dataclass
class Segmentation:
    mask: np.ndarray            # uint8, 255 = fruit, same height/width as the input
    contour: np.ndarray | None  # outline in input-image pixels
    area_frac: float            # fruit area / image area
    method: str                 # "background-model" or "grabcut"
    ok: bool
    reason: str = ""


def _to_work(bgr: np.ndarray) -> tuple[np.ndarray, float]:
    h, w = bgr.shape[:2]
    scale = min(1.0, WORK_SIDE / max(h, w))
    if scale < 1.0:
        bgr = cv2.resize(bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    return bgr, scale


def _border_pixels(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    k = max(2, int(BORDER_FRAC * min(h, w)))
    return np.concatenate([img[:k].reshape(-1, 3), img[-k:].reshape(-1, 3),
                           img[:, :k].reshape(-1, 3), img[:, -k:].reshape(-1, 3)])


def _largest_component(binary: np.ndarray) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n <= 1:
        return np.zeros_like(binary)
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(labels == best, 255, 0).astype(np.uint8)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    flood = mask.copy()
    ff_mask = np.zeros((h + 2, w + 2), np.uint8)
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if flood[seed[1], seed[0]] == 0:
            cv2.floodFill(flood, ff_mask, seed, 255)
    return mask | cv2.bitwise_not(flood)


def _clean(mask: np.ndarray) -> np.ndarray:
    open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)
    return _fill_holes(_largest_component(mask))


def _background_model(work: np.ndarray) -> tuple[np.ndarray, float]:
    lab = cv2.cvtColor(work.astype(np.float32) / 255.0, cv2.COLOR_BGR2Lab)
    bg = np.median(_border_pixels(lab), axis=0)
    d_chroma = np.hypot(lab[..., 1] - bg[1], lab[..., 2] - bg[2])
    d_light = np.maximum(0.0, np.abs(lab[..., 0] - bg[0]) - SHADOW_TOLERANCE_L)
    dist = np.hypot(d_chroma, d_light)
    contrast = float(np.percentile(dist, 99))
    if contrast < MIN_CONTRAST:
        return np.zeros(work.shape[:2], np.uint8), contrast
    d8 = np.clip(dist * (255.0 / max(contrast, 1e-6)), 0, 255).astype(np.uint8)
    otsu, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    floor = MIN_CONTRAST * 255.0 / contrast  # never accept differences below MIN_CONTRAST
    _, binary = cv2.threshold(d8, max(otsu, floor), 255, cv2.THRESH_BINARY)
    return _clean(binary), contrast


def _grabcut(work: np.ndarray) -> np.ndarray:
    h, w = work.shape[:2]
    rect = (int(0.1 * w), int(0.1 * h), int(0.8 * w), int(0.8 * h))
    gc = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(work, gc, rect, bgd, fgd, 4, cv2.GC_INIT_WITH_RECT)
    binary = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    return _clean(binary)


def segment_fruit(bgr: np.ndarray) -> Segmentation:
    """Segment the single item in a product photo."""
    if bgr is None or bgr.ndim != 3:
        raise ValueError("expected a BGR colour image")
    work, scale = _to_work(bgr)
    mask, contrast = _background_model(work)
    method = "background-model"
    frac = float(np.count_nonzero(mask)) / mask.size
    if contrast < MIN_CONTRAST:
        return Segmentation(np.zeros(bgr.shape[:2], np.uint8), None, 0.0, method, False, "no item stands out from the background")
    if not MIN_AREA_FRAC <= frac <= MAX_AREA_FRAC:
        mask, method = _grabcut(work), "grabcut"
        frac = float(np.count_nonzero(mask)) / mask.size

    ok = MIN_AREA_FRAC <= frac <= MAX_AREA_FRAC
    full = cv2.resize(mask, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_NEAREST) if scale < 1.0 else mask
    contours, _ = cv2.findContours(full, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contour = max(contours, key=cv2.contourArea) if contours else None
    reason = "" if ok else f"item covers {frac:.1%} of the frame, outside {MIN_AREA_FRAC:.0%}-{MAX_AREA_FRAC:.0%}"
    return Segmentation(full, contour, frac, method, ok, reason)

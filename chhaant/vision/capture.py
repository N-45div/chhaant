"""Is this photo usable evidence? Checks that run before a look is allowed to count.

A blurred, glared, badly exposed or empty photo still gets a score from the
quality model, and that score is noise. So every capture is measured first, at
the segmentation's 512-px working size (the same numbers for a 512-px replay
photo and a 12 MP camera frame):

* blur: outline sharpness, the strongest gradients along the item's outline
  divided by the item/backdrop contrast (roughly one over the edge width in
  pixels). Every item has an outline; defocus and motion blur widen it.
* glare: the share of the item's convex hull blown out in every channel
* overexposure: the share of item pixels clipped in any channel, which skews
  its colour. Only the item counts: TR-6's white backdrop is often clipped
  while the fruit is perfectly exposed.
* darkness: the backdrop's median grey level
* framing: the share of the outline lying on the frame's edge (item cut off)
* presence: the item's grey-level contrast with the backdrop; a shadow left on
  an empty turntable is faint, any real fruit (dark rotten ones most of all)
  stands out

Safety rule: a flag must never turn a dark or smooth rotten item into "bad
photo" instead of "defective". So exposure is judged on the backdrop, never on
the item, and surface detail (the variance of the Laplacian inside the item,
still measured) is not a blur test: blur erases it, but so does a blackened
fruit. Both rules flagged sharp photos of spoiled fruit in calibration.

Thresholds come from eval/capture_failures.py: the 0.5th/99.5th percentile of
real TR-6 and avocado photos on a calibration split, then checked on held-out
photos and on synthetic blur, glare, exposure, framing and empty-frame failures.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from chhaant.vision.segment import WORK_SIDE, segment_fruit

# Calibrated by eval/capture_failures.py (see eval/results/capture_failures.md).
THRESHOLDS = {"min_contrast": 27.4, "min_edge_sharpness": 0.1768, "max_glare": 0.02, "min_backdrop_grey": 135.0, "max_item_clipped": 0.05,
              "max_outline_on_edge": 0.02}

BAND_PX = 8       # half-width of the band searched for the edge: wide enough for a GrabCut-sized mask error
CLIPPED = 250     # every channel at or above this: blown out


@dataclass
class CaptureCheck:
    ok: bool
    problems: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def summary(self) -> str:
        return "; ".join(self.problems)


def _work(bgr: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h, w = bgr.shape[:2]
    scale = min(1.0, WORK_SIDE / max(h, w))
    if scale < 1.0:
        size = (round(w * scale), round(h * scale))
        return cv2.resize(bgr, size, interpolation=cv2.INTER_AREA), cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST)
    return bgr, mask


def capture_metrics(bgr: np.ndarray, mask: np.ndarray) -> dict:
    """Sharpness, glare, exposure and framing numbers for one photo and its item mask."""
    work, m = _work(bgr, mask)
    item = m > 0
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    out = {"frame_clipped": float(np.mean(work.min(axis=2) >= CLIPPED)),
           "frame_grey": float(np.median(gray))}
    if item.sum() < 50:
        return out
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * BAND_PX + 1,) * 2)
    inner = cv2.erode(m, k) > 0
    outer = cv2.dilate(m, k) > 0
    band = outer & ~inner
    backdrop = ~cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))).astype(bool)
    g = gray.astype(np.float32)
    grad = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)) / 8.0
    contrast = abs(float(np.median(g[inner])) - float(np.median(g[backdrop]))) if inner.any() and backdrop.any() else 0.0
    out["contrast"] = contrast
    out["backdrop_grey"] = float(np.median(g[backdrop])) if backdrop.any() else out["frame_grey"]
    out["edge_sharpness"] = float(np.percentile(grad[band], 98)) / max(contrast, 1.0) if band.any() else 0.0
    out["texture"] = float(cv2.Laplacian(g, cv2.CV_32F)[inner].var()) if inner.any() else 0.0
    # Inside the item's convex hull: a blown-out highlight is as white as the backdrop, so
    # segmentation carves it out of the mask itself.
    hull = np.zeros_like(m)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.fillPoly(hull, [cv2.convexHull(np.vstack(contours))], 255)
    out["glare"] = float(np.mean(work.min(axis=2)[hull > 0] >= CLIPPED))
    out["item_grey"] = float(np.median(gray[item]))
    out["item_clipped"] = float(np.mean(work.max(axis=2)[item] >= CLIPPED))
    border = np.zeros_like(item)
    border[[0, -1], :] = True
    border[:, [0, -1]] = True
    # Erode with nothing beyond the frame, so the outline running along the frame edge counts.
    outline = item & ~(cv2.erode(m, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0) > 0)
    out["outline_on_edge"] = float((outline & border).sum()) / max(1, int(outline.sum()))
    return out


def judge(m: dict, t: dict = THRESHOLDS) -> list[str]:
    """Every reason the measured photo cannot count as evidence (empty when it can)."""
    problems = []  # causes first: an over- or under-exposed photo also loses its contrast and its sharp outline
    if m.get("backdrop_grey", 255.0) < t["min_backdrop_grey"]:
        problems.append(f"too dark (backdrop grey {m['backdrop_grey']:.0f})")
    # Glare clips every channel too; overexposure is the clipping that glare does not explain.
    if m.get("item_clipped", 0.0) - max(m.get("glare", 0.0), 0.0) > t["max_item_clipped"]:
        problems.append(f"overexposed ({m['item_clipped']:.0%} of the item clipped)")
    if m.get("glare", 0.0) > t["max_glare"]:
        problems.append(f"glare on {m['glare']:.0%} of the item")
    if not problems and m.get("contrast", 255.0) < t["min_contrast"]:
        return [f"no usable item: nothing stands out clearly (contrast {m['contrast']:.0f})"]
    if m.get("outline_on_edge", 0.0) > t["max_outline_on_edge"]:
        problems.append(f"item cut off by the frame edge ({m['outline_on_edge']:.0%} of its outline)")
    if m.get("edge_sharpness", 1.0) < t["min_edge_sharpness"]:
        problems.append(f"blurred (outline sharpness {m['edge_sharpness']:.3f} < {t['min_edge_sharpness']:.3f})")
    return problems


def check_capture(bgr: np.ndarray, seg=None) -> CaptureCheck:
    """Whether a photo can count as evidence, and if not, every reason why."""
    seg = seg if seg is not None else segment_fruit(bgr)
    if not seg.ok:
        return CaptureCheck(False, [f"no usable item: {seg.reason}"], {})
    m = capture_metrics(bgr, seg.mask)
    problems = judge(m)
    return CaptureCheck(not problems, problems, m)

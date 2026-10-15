"""Is this photo usable evidence? Checks that run before a look is allowed to count.

A blurred, glared, badly exposed or empty photo still gets a score from the
quality model, and that score is noise. So every capture is measured first, at
the segmentation's 512-px working size (the same numbers for a 512-px replay
photo and a 12 MP camera frame):

* outline sharpness: the strongest gradients along the item's outline, divided
  by the item/backdrop contrast; roughly one over the edge width in pixels.
  Defocus and motion blur widen the edge.
* surface detail: the variance of the Laplacian inside the item. Blur erases
  it, but so does a smooth or blackened fruit, so it only decides when the
  outline is marginal (below twice its threshold). A flag must never turn a
  dark, rotten item into "bad photo" instead of "defective".
* glare: the share of item pixels blown out in every channel
* exposure: the backdrop's median grey level (never the item's: a rotten fruit
  is dark, and must be called defective, not written off as a bad photo), and
  the share of the frame clipped
* framing: the share of the outline lying on the frame's edge (item cut off)

Thresholds come from eval/capture_failures.py: the 0.5th/99.5th percentile of
real TR-6 and avocado photos on a calibration split, then checked on held-out
photos and on synthetic blur, glare, exposure and framing failures.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from chhaant.vision.segment import WORK_SIDE, segment_fruit

# Calibrated by eval/capture_failures.py (see eval/results/capture_failures.md).
THRESHOLDS = {"min_edge_sharpness": 0.10, "min_texture": 5.0, "max_glare": 0.08, "min_backdrop_grey": 60.0,
              "max_frame_clipped": 0.40, "max_outline_on_edge": 0.10}

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
    border = np.zeros_like(item)
    border[[0, -1], :] = True
    border[:, [0, -1]] = True
    # Erode with nothing beyond the frame, so the outline running along the frame edge counts.
    outline = item & ~(cv2.erode(m, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0) > 0)
    out["outline_on_edge"] = float((outline & border).sum()) / max(1, int(outline.sum()))
    return out


def judge(m: dict, t: dict = THRESHOLDS) -> list[str]:
    """Every reason the measured photo cannot count as evidence (empty when it can)."""
    problems = []
    if m.get("edge_sharpness", 1.0) < t["min_edge_sharpness"]:
        problems.append(f"blurred (outline sharpness {m['edge_sharpness']:.3f} < {t['min_edge_sharpness']:.3f})")
    elif m.get("texture", 1e9) < t["min_texture"] and m.get("edge_sharpness", 1.0) < 2 * t["min_edge_sharpness"]:
        problems.append(f"blurred (surface detail {m['texture']:.1f} < {t['min_texture']:.1f})")
    if m.get("glare", 0.0) > t["max_glare"]:
        problems.append(f"glare on {m['glare']:.0%} of the item")
    if m.get("backdrop_grey", 255.0) < t["min_backdrop_grey"]:
        problems.append(f"too dark (backdrop grey {m['backdrop_grey']:.0f})")
    if m.get("frame_clipped", 0.0) > t["max_frame_clipped"]:
        problems.append(f"overexposed ({m['frame_clipped']:.0%} of the frame clipped)")
    if m.get("outline_on_edge", 0.0) > t["max_outline_on_edge"]:
        problems.append(f"item cut off by the frame edge ({m['outline_on_edge']:.0%} of its outline)")
    return problems


def check_capture(bgr: np.ndarray, seg=None) -> CaptureCheck:
    """Whether a photo can count as evidence, and if not, every reason why."""
    seg = seg if seg is not None else segment_fruit(bgr)
    if not seg.ok:
        return CaptureCheck(False, [f"no usable item: {seg.reason}"], {})
    m = capture_metrics(bgr, seg.mask)
    problems = judge(m)
    return CaptureCheck(not problems, problems, m)

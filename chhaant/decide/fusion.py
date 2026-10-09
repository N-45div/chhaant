"""Turn per-view defect scores into one per-item score that demands agreement.

A real defect is a patch of skin. Neighbouring camera angles see it too: a
surface point stays within 60 degrees of head-on for about five of TR-6's
22.5-degree steps. Glare, a stem scar seen edge-on, or a segmentation slip
usually shows in one view only. So rather than trusting the worst single view
(which piled up false alarms on TR-6 tomatoes as more views were added), a
defect counts when the captured views around one angle agree: the median of a
neighbourhood of at least three views. One glare beside two clean views has a
median near zero; a defect seen from three adjacent angles keeps a high one.
A mean does not work here: 0.95 next to 0.05 averages to a dithering 0.5.
"""

import numpy as np

DEFAULT_WINDOW_DEG = 45.0


def angular_gap(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def neighbours(views: dict[float, float], azimuth: float, window_deg: float = DEFAULT_WINDOW_DEG) -> list[float]:
    """Captured azimuths within ``window_deg`` of ``azimuth`` (including itself)."""
    return [a for a in views if angular_gap(a, azimuth) <= window_deg]


MIN_SUPPORT = 3


def agreement(views: dict[float, float], window_deg: float = DEFAULT_WINDOW_DEG,
              min_support: int = MIN_SUPPORT) -> tuple[float, int]:
    """Best median score over a neighbourhood of at least ``min_support`` captured views.

    Returns (score, support). With no neighbourhood that large yet, returns (0.0, 0):
    nothing has been confirmed.
    """
    best, support = 0.0, 0
    for a in views:
        near = neighbours(views, a, window_deg)
        if len(near) >= min_support:
            score = float(np.median([views[n] for n in near]))
            if score > best:
                best, support = score, len(near)
    return best, support


def fuse(scores: list[float], method: str) -> float:
    """Order-free baselines for comparison: max, mean, median, top2 (mean of the two highest)."""
    s = np.sort(np.asarray(scores, float))[::-1]
    if method == "max":
        return float(s[0])
    if method == "mean":
        return float(s.mean())
    if method == "median":
        return float(np.median(s))
    if method == "top2":
        return float(s[:2].mean())
    raise ValueError(f"unknown fusion method: {method}")

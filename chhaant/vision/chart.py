"""Colour correction from a ColorChecker in frame (OpenCV 5 ``cv2.mcc`` + ``cv2.ccm``).

When a 24-patch ColorChecker is visible, ``cv2.mcc`` finds it and ``cv2.ccm``
fits a colour-correction matrix to its known values. That beats backdrop white
balance: it corrects every hue, not only the neutral axis, so ripeness colour
means the same thing under any lamp or phone.

Two behaviours of OpenCV 5.0.0 that this module handles (found while building
it, with a synthetic chart under a known colour cast):

* The classical chart detector is randomised. A single attempt found a perfect
  synthetic chart only 40-70% of the time, and neither ``cv2.setRNGSeed`` nor a
  single thread made it repeatable. We try several fresh detectors.
* The matrix is fitted from RGB patch values (``getChartsRGB`` rows are R, G,
  B), but ``ColorCorrectionModel.correctImage`` expects a BGR image. Passing RGB
  made a cast chart worse (mean dE76 18.6 -> 33.8); passing BGR fixes it
  (18.6 -> 3.9).
"""

from dataclasses import dataclass

import cv2
import numpy as np

DEFAULT_ATTEMPTS = 12


@dataclass
class ChartCorrection:
    model: "cv2.ccm.ColorCorrectionModel"
    patches_rgb: np.ndarray  # (24, 3) measured patch means, RGB 0-255
    loss: float              # fit error on the patches (CIEDE2000)
    attempts: int            # detector attempts it took to find the chart


def find_chart_patches(bgr: np.ndarray, attempts: int = DEFAULT_ATTEMPTS) -> tuple[np.ndarray | None, int]:
    """Mean RGB of the 24 ColorChecker patches, or None when no chart is found."""
    for n in range(1, attempts + 1):
        detector = cv2.mcc.CCheckerDetector.create()
        if detector.process(bgr, 1):
            stats = detector.getBestColorChecker().getChartsRGB()  # rows: patch x channel; col 1 = mean
            return stats[:, 1].reshape(24, 3).astype(np.float64), n
    return None, attempts


def fit_correction(bgr: np.ndarray, attempts: int = DEFAULT_ATTEMPTS) -> ChartCorrection | None:
    """Fit a 3x3 colour-correction matrix to the chart in ``bgr``; None if no chart is visible."""
    patches, tries = find_chart_patches(bgr, attempts)
    if patches is None:
        return None
    model = cv2.ccm.ColorCorrectionModel((patches / 255.0).reshape(24, 1, 3), cv2.ccm.COLORCHECKER_MACBETH)
    model.setColorSpace(cv2.ccm.COLOR_SPACE_SRGB)
    model.setCcmType(cv2.ccm.CCM_LINEAR)
    model.setDistance(cv2.ccm.DISTANCE_CIE2000)
    model.setLinearization(cv2.ccm.LINEARIZATION_GAMMA)
    model.setLinearizationGamma(2.2)
    model.compute()
    return ChartCorrection(model, patches, float(model.getLoss()), tries)


def apply_correction(correction: ChartCorrection, bgr: np.ndarray) -> np.ndarray:
    """Colour-correct a BGR photo (``correctImage`` takes BGR, see module notes)."""
    return correction.model.correctImage(bgr)

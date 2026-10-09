"""A synthetic ColorChecker under a known colour cast must be found and corrected."""

import cv2
import numpy as np

from chhaant.vision.chart import apply_correction, fit_correction

# sRGB values of the 24 ColorChecker Classic patches, row by row
REF_RGB = [(115, 82, 68), (194, 150, 130), (98, 122, 157), (87, 108, 67), (133, 128, 177), (103, 189, 170),
           (214, 126, 44), (80, 91, 166), (193, 90, 99), (94, 60, 108), (157, 188, 64), (224, 163, 46),
           (56, 61, 150), (70, 148, 73), (175, 54, 60), (231, 199, 31), (187, 86, 149), (8, 133, 161),
           (243, 243, 242), (200, 200, 200), (160, 160, 160), (122, 122, 121), (85, 85, 85), (52, 52, 52)]
CELL, GAP, OFF = 70, 14, 100


def patch_xy(i):
    r, c = divmod(i, 6)
    return OFF + GAP + c * (CELL + GAP), OFF + GAP + r * (CELL + GAP)


def chart_scene():
    w, h = 6 * CELL + 7 * GAP, 4 * CELL + 5 * GAP
    img = np.full((h + 2 * OFF, w + 2 * OFF, 3), (215, 210, 205), np.uint8)
    cv2.rectangle(img, (OFF, OFF), (OFF + w, OFF + h), (20, 20, 20), -1)
    for i, rgb in enumerate(REF_RGB):
        x, y = patch_xy(i)
        cv2.rectangle(img, (x, y), (x + CELL, y + CELL), rgb[::-1], -1)
    return img


def with_cast(bgr):
    """A warm, slightly contrasty camera: per-channel gains and a gamma change."""
    return np.clip(((bgr.astype(np.float32) / 255) ** 1.15) * np.array([1.18, 0.95, 0.80]) * 255, 0, 255).astype(np.uint8)


def mean_delta_e(bgr):
    measured = np.array([bgr[y + 10:y + CELL - 10, x + 10:x + CELL - 10].reshape(-1, 3).mean(0)[::-1]
                         for x, y in map(patch_xy, range(24))], np.float32)
    lab = lambda rgb: cv2.cvtColor(np.asarray(rgb, np.float32).reshape(-1, 1, 3) / 255, cv2.COLOR_RGB2Lab).reshape(-1, 3)
    return float(np.linalg.norm(lab(measured) - lab(REF_RGB), axis=1).mean())


def test_chart_under_a_colour_cast_is_corrected():
    cast = with_cast(chart_scene())
    before = mean_delta_e(cast)
    correction = fit_correction(cast)
    assert correction is not None
    after = mean_delta_e(apply_correction(correction, cast))
    assert before > 15
    assert after < 6 and after < 0.4 * before


def test_no_chart_means_no_correction():
    plain = np.full((480, 640, 3), (215, 210, 205), np.uint8)
    cv2.circle(plain, (320, 240), 90, (40, 40, 200), -1)
    assert fit_correction(plain, attempts=3) is None

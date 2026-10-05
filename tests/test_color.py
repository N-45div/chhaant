import numpy as np
import pytest

from chhaant.vision.color import colour_stats, white_balance_from_background


def patch(bgr, size=(120, 120)):
    img = np.zeros((*size, 3), np.uint8)
    img[:] = bgr
    mask = np.full(size, 255, np.uint8)
    return img, mask


def test_srgb_red_matches_reference_lab():
    stats = colour_stats(*patch((0, 0, 255)))
    # Reference CIELAB D65 for sRGB (255, 0, 0): 53.24, 80.09, 67.20
    assert stats.L == pytest.approx(53.24, abs=0.5)
    assert stats.a == pytest.approx(80.09, abs=0.5)
    assert stats.b == pytest.approx(67.20, abs=0.5)
    assert stats.hue_deg == pytest.approx(40.0, abs=0.5)


def test_yellow_and_green_hues_are_ordered():
    yellow = colour_stats(*patch((0, 220, 240)))
    green = colour_stats(*patch((40, 160, 60)))
    assert 90 < yellow.hue_deg < 110
    assert green.hue_deg > yellow.hue_deg
    assert yellow.a_over_b < 0.0 < colour_stats(*patch((30, 60, 200))).a_over_b


def test_dark_spots_are_counted():
    img, mask = patch((40, 200, 230))
    img[:, :30] = (10, 30, 40)  # a quarter of the item blackened
    assert colour_stats(img, mask, erode_px=0).dark_frac == pytest.approx(0.25, abs=0.01)


def test_white_balance_neutralises_a_tinted_backdrop():
    img = np.full((300, 300, 3), (240, 205, 195), np.uint8)  # bluish-purple cast on a white backdrop
    mask = np.zeros((300, 300), np.uint8)
    mask[100:200, 100:200] = 255
    img[mask > 0] = (30, 40, 190)
    balanced = white_balance_from_background(img, mask)
    bg = balanced[10, 10].astype(int)
    assert bg.max() - bg.min() <= 2

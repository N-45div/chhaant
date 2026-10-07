import cv2
import numpy as np
import pytest

from chhaant.vision.defects import defect_map, summarise


def item(colour, size=400, radius=150):
    img = np.full((size, size, 3), (228, 226, 224), np.uint8)
    mask = np.zeros((size, size), np.uint8)
    cv2.circle(mask, (size // 2, size // 2), radius, 255, -1)
    img[mask > 0] = colour
    noise = np.random.default_rng(1).normal(0, 2.5, img.shape)
    return np.clip(img + noise, 0, 255).astype(np.uint8), mask


def test_clean_red_tomato_has_no_defects():
    img, mask = item((40, 45, 190))
    s = summarise(defect_map(img, mask), mask)
    assert s.area_frac < 0.01 and s.blobs == 0


def test_deep_red_is_dark_but_not_dull():
    img, mask = item((25, 25, 110))  # L* ~ 23, but strongly coloured
    assert summarise(defect_map(img, mask), mask).area_frac < 0.02


def test_brown_rot_patch_is_found_as_one_blob():
    img, mask = item((40, 45, 190))
    cv2.circle(img, (230, 180), 45, (35, 50, 65), -1)  # dark, dull brown: ~9% of the item
    s = summarise(defect_map(img, mask), mask)
    assert s.blobs == 1
    assert s.area_frac == pytest.approx(45**2 / 150**2, abs=0.03)


def test_item_blackened_all_over_scores_high():
    img, mask = item((30, 32, 34))
    assert summarise(defect_map(img, mask), mask).area_frac > 0.9


def test_small_spots_on_a_light_yellow_banana():
    img, mask = item((60, 215, 235))
    for x, y in [(150, 160), (240, 230), (200, 290)]:
        cv2.circle(img, (x, y), 9, (60, 140, 160), -1)  # darker, still coloured: only the spot test sees these
    s = summarise(defect_map(img, mask), mask)
    assert s.blobs == 3


def test_green_guava_skin_is_not_flagged():
    img, mask = item((70, 140, 95))  # L* ~ 51, chroma ~ 28
    assert summarise(defect_map(img, mask), mask).area_frac < 0.02

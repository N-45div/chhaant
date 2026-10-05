import cv2
import numpy as np

from chhaant.vision.segment import segment_fruit


def scene(fruit_bgr, size=(600, 800), bg=(232, 228, 226), shadow=True):
    """A plain light background with one round 'fruit' and an optional grey shadow."""
    h, w = size
    img = np.full((h, w, 3), bg, np.uint8)
    if shadow:
        cv2.ellipse(img, (w // 2 + 60, h // 2 + 120), (170, 60), 0, 0, 360, (190, 186, 184), -1)
        img = cv2.GaussianBlur(img, (31, 31), 0)
    truth = np.zeros((h, w), np.uint8)
    cv2.circle(truth, (w // 2, h // 2), 150, 255, -1)
    img[truth > 0] = fruit_bgr
    noise = np.random.default_rng(0).normal(0, 3, img.shape)
    return np.clip(img + noise, 0, 255).astype(np.uint8), truth


def iou(a, b):
    a, b = a > 0, b > 0
    return (a & b).sum() / max(1, (a | b).sum())


def test_red_fruit_found_and_shadow_ignored():
    img, truth = scene((40, 40, 200))
    seg = segment_fruit(img)
    assert seg.ok and seg.method == "background-model"
    assert iou(seg.mask, truth) > 0.93


def test_blackened_fruit_is_still_found():
    img, truth = scene((35, 38, 40))
    seg = segment_fruit(img)
    assert seg.ok
    assert iou(seg.mask, truth) > 0.93


def test_mask_matches_large_input_size():
    img, truth = scene((40, 160, 60), size=(1600, 1200))
    seg = segment_fruit(img)
    assert seg.mask.shape == img.shape[:2]
    assert iou(seg.mask, truth) > 0.9


def test_empty_background_reports_no_item():
    img = np.full((480, 640, 3), (230, 228, 225), np.uint8)
    seg = segment_fruit(img)
    assert not seg.ok
    assert "no item" in seg.reason

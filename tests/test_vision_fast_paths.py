"""The 12 MP fast paths must give exactly what the original full-frame code gave.

``item_crop`` feeds training and inference alike, and the colour readings feed
the validated avocado forecast, so "close" is not enough: the reference
implementations below are the code as it was before the region-of-interest
rewrite, and every output is compared for equality.
"""

import glob
import os

import cv2
import numpy as np
import pytest

from chhaant.decide.shelf import colour_reading
from chhaant.vision.color import colour_stats, white_balance_from_background
from chhaant.vision.crop import MARGIN, MODEL_SIDE, NEUTRAL, RIM_FRAC, item_crop
from chhaant.vision.segment import segment_fruit

ROOT = os.path.join(os.path.dirname(__file__), "..")


def reference_item_crop(bgr, mask=None, side=MODEL_SIDE):
    h, w = bgr.shape[:2]
    if mask is None or not np.any(mask):
        cx, cy, half = w / 2, h / 2, max(w, h) / 2
        work = bgr
    else:
        x, y, bw, bh = cv2.boundingRect(mask)
        r = max(1, round(RIM_FRAC * max(bw, bh)))
        keep = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2)) > 0
        work = bgr.copy()
        work[~keep] = NEUTRAL
        cx, cy = x + bw / 2, y + bh / 2
        half = max(bw, bh) * (0.5 + MARGIN)
    x0, y0 = int(round(cx - half)), int(round(cy - half))
    size = max(1, int(round(2 * half)))
    pad = max(0, -x0, -y0, x0 + size - w, y0 + size - h)
    if pad:
        work = cv2.copyMakeBorder(work, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=NEUTRAL)
        x0, y0 = x0 + pad, y0 + pad
    crop = work[y0:y0 + size, x0:x0 + size]
    interp = cv2.INTER_AREA if size > side else cv2.INTER_LINEAR
    return cv2.resize(crop, (side, side), interpolation=interp)


def reference_white_balance(bgr, mask, margin_px=15):
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * margin_px + 1, 2 * margin_px + 1))
    background = cv2.dilate(mask, k) == 0
    if background.sum() < 500:
        return bgr.copy()
    ref = np.median(bgr[background].astype(np.float32), axis=0)
    gains = ref.mean() / np.maximum(ref, 1.0)
    return np.clip(bgr.astype(np.float32) * gains, 0, 255).astype(np.uint8)


def synthetic_scenes():
    rng = np.random.default_rng(7)
    out = []
    for (h, w), centre, axes, value in [
        ((480, 640), (320, 240), (90, 70), 255),   # centred
        ((480, 640), (600, 30), (80, 60), 255),    # cut by the top-right corner
        ((300, 900), (5, 150), (40, 140), 1),      # 0/1 mask on the left edge
        ((400, 400), (200, 200), (300, 300), 255),  # covers the whole frame: no backdrop left
        ((256, 256), (128, 128), (3, 2), 255),     # a tiny item
    ]:
        img = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        img[:, :, 1] = np.clip(img[:, :, 1].astype(int) + 60, 0, 255)  # a tinted backdrop, so the gains matter
        mask = np.zeros((h, w), np.uint8)
        cv2.ellipse(mask, centre, axes, 25, 0, 360, value, -1)
        out.append((img, mask))
    img = rng.integers(0, 256, (200, 300, 3), dtype=np.uint8)
    out.append((img, np.zeros((200, 300), np.uint8)))  # nothing segmented
    return out


def real_scenes():
    paths = (sorted(glob.glob(os.path.join(ROOT, "data", "tr6_full", "*.jpg")))[:4]
             + sorted(glob.glob(os.path.join(ROOT, "data", "tr6", "tr6_512", "*", "*.jpg")))[::400][:6]
             + sorted(glob.glob(os.path.join(ROOT, "data", "avocado", "*.jpg")))[::150][:4])
    out = []
    for p in paths:
        img = cv2.imread(p)
        seg = segment_fruit(img)
        if seg.ok:
            out.append((img, seg.mask))
    return out


SCENES = synthetic_scenes() + real_scenes()


@pytest.mark.parametrize("img,mask", SCENES)
def test_item_crop_matches_the_full_frame_version_exactly(img, mask):
    assert np.array_equal(item_crop(img, mask), reference_item_crop(img, mask))


@pytest.mark.parametrize("img,mask", SCENES)
def test_white_balance_matches_the_full_frame_version_exactly(img, mask):
    assert np.array_equal(white_balance_from_background(img, mask), reference_white_balance(img, mask))


def outcome(fn):
    try:
        return fn()
    except ValueError as err:  # e.g. an item so small the edge trim leaves no pixels
        return f"ValueError: {err}"


@pytest.mark.parametrize("img,mask", [s for s in SCENES if np.any(s[1])])
def test_colour_reading_matches_the_full_frame_version_exactly(img, mask):
    assert outcome(lambda: colour_reading(img, mask)) == outcome(lambda: colour_stats(reference_white_balance(img, mask), mask))


def test_real_photos_were_part_of_the_check():
    if not os.path.isdir(os.path.join(ROOT, "data", "tr6")):
        pytest.skip("no TR-6 data here")
    assert len(SCENES) > len(synthetic_scenes())

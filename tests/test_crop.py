import cv2
import numpy as np

from chhaant.vision.crop import MODEL_SIDE, NEUTRAL, item_crop


def scene():
    img = np.full((480, 640, 3), (230, 228, 225), np.uint8)
    mask = np.zeros((480, 640), np.uint8)
    cv2.circle(mask, (500, 120), 60, 255, -1)  # off-centre, near the top edge
    img[mask > 0] = (40, 40, 200)
    return img, mask


def test_crop_is_square_and_centred_on_the_item():
    img, mask = scene()
    crop = item_crop(img, mask)
    assert crop.shape == (MODEL_SIDE, MODEL_SIDE, 3)
    centre = crop[MODEL_SIDE // 2, MODEL_SIDE // 2]
    assert tuple(int(v) for v in centre) == (40, 40, 200)


def test_backdrop_is_greyed_out():
    img, mask = scene()
    crop = item_crop(img, mask)
    assert tuple(int(v) for v in crop[2, 2]) == NEUTRAL
    backdrop_left = np.all(crop == (230, 228, 225), axis=-1).mean()
    assert backdrop_left < 0.02  # only the thin rim kept around the outline


def test_item_fills_most_of_the_crop():
    img, mask = scene()
    crop = item_crop(img, mask)
    red = np.all(np.abs(crop.astype(int) - (40, 40, 200)) < 30, axis=-1).mean()
    assert 0.45 < red < 0.65  # a disc in a square with a 12% margin: pi/4 / 1.24^2 ~ 0.51


def test_without_a_mask_the_whole_image_is_letterboxed():
    img, _ = scene()
    crop = item_crop(img, None)
    assert crop.shape == (MODEL_SIDE, MODEL_SIDE, 3)
    assert tuple(int(v) for v in crop[1, MODEL_SIDE // 2]) == NEUTRAL  # padding above the landscape image

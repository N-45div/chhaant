import cv2
import numpy as np

from chhaant.vision.capture import check_capture


def photo(colour=(40, 60, 190), texture=12.0, backdrop=(228, 226, 224), centre=(192, 256), seed=0):
    """A camera-like photo: a textured fruit on a plain backdrop, both with sensor noise."""
    rng = np.random.default_rng(seed)
    img = np.empty((512, 384, 3), np.float32)
    img[:] = backdrop
    mask = np.zeros((512, 384), np.uint8)
    cv2.ellipse(mask, centre, (110, 130), 0, 0, 360, 255, -1)
    detail = cv2.GaussianBlur(rng.normal(0, texture, (512, 384)).astype(np.float32), (0, 0), 1.2)
    img[mask > 0] = np.asarray(colour, np.float32) + detail[mask > 0, None]
    img += rng.normal(0, 2.0, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def test_a_sharp_photo_is_usable():
    c = check_capture(photo())
    assert c.ok, c.problems


def test_a_dark_smooth_rotten_item_is_still_usable():
    # A blackened fruit must be scored (and called defective), never written off as a bad photo.
    c = check_capture(photo(colour=(22, 24, 28), texture=1.5))
    assert c.ok, c.problems


def test_blur_is_caught():
    c = check_capture(cv2.GaussianBlur(photo(), (0, 0), 3))
    assert not c.ok and any("blurred" in p for p in c.problems)


def test_an_empty_turntable_is_caught():
    rng = np.random.default_rng(1)
    empty = np.clip(np.full((512, 384, 3), (228, 226, 224), np.float32) + rng.normal(0, 2, (512, 384, 3)), 0, 255)
    c = check_capture(empty.astype(np.uint8))
    assert not c.ok and c.problems[0].startswith("no usable item")


def test_underexposure_is_caught_by_the_backdrop():
    c = check_capture((photo().astype(np.float32) * 0.2).astype(np.uint8))
    assert not c.ok and any("too dark" in p or "no usable item" in p for p in c.problems)


def test_overexposure_and_glare_are_caught():
    bright = np.clip(photo().astype(np.float32) * 3, 0, 255).astype(np.uint8)
    assert any("overexposed" in p or "glare" in p for p in check_capture(bright).problems)
    glared = photo()
    cv2.ellipse(glared, (170, 220), (60, 45), -30, 0, 360, (255, 255, 255), -1)
    assert any("glare" in p for p in check_capture(glared).problems)


def test_an_item_cut_off_by_the_frame_is_caught():
    c = check_capture(photo(centre=(384, 256)))
    assert not c.ok and any("cut off" in p for p in c.problems)

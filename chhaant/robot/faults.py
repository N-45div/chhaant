"""Simulated camera faults: what the cell does with a bad photo, shown and tested.

The failures are the ones eval/capture_failures.py measures (blur, glare,
exposure, an empty turntable, an item cut off by the frame). ``FaultyTurntable``
spoils the photos at chosen angles; the avocado inspector spoils a chosen side.
A spoiled photo's reference carries its fault ("tr6:<file>#motion 17"), so the
evidence view shows the degraded pixels the cell was given, not the original.

Only the names in FAULTS are accepted, since references arrive in URLs.
"""

import cv2
import numpy as np

from chhaant.robot.turntable import Capture
from chhaant.vision.segment import segment_fruit

FAULTS = ("defocus 1.5", "defocus 3", "motion 9", "motion 17", "glare 10%", "glare 20%",
          "dark x0.2", "bright x3", "empty", "cut off 40%")

# The "camera faults" demo run: one blurred side view (the cell looks elsewhere), glare at
# every angle (three failures in a row stop the inspection and a person is asked), and one
# avocado side cut off by the frame (its forecast comes from the other side).
DEMO_FAULTS = {"T1": {0.0: "motion 17"}, "T3": {"every": "glare 20%"}, "A2": {1: "cut off 40%"}}


def _px(img, v):  # sizes are given at 512 px and scale with the photo
    return v * max(img.shape[:2]) / 512


def degrade(img: np.ndarray, mask: np.ndarray, cond: str) -> np.ndarray:
    """The photo as a faulty capture would have taken it."""
    if cond == "clean":
        return img
    kind, arg = cond.split(" ")[0], cond.split(" ")[-1]
    if kind == "defocus":
        return cv2.GaussianBlur(img, (0, 0), _px(img, float(arg)))
    if kind == "motion":
        n = int(round(_px(img, float(arg)))) | 1
        k = np.zeros((n, n), np.float32)
        k[n // 2, :] = 1.0 / n
        return cv2.filter2D(img, -1, k)
    if kind == "glare":  # a blown-out highlight covering a share of the item
        x, y, w, h = cv2.boundingRect(mask)
        b = np.sqrt(float(arg.rstrip("%")) / 100 * np.count_nonzero(mask) / (np.pi * 1.4))
        spot = np.zeros(mask.shape, np.float32)
        cv2.ellipse(spot, (int(x + 0.42 * w), int(y + 0.38 * h)), (int(1.4 * b), int(b)), -30, 0, 360, 1.0, -1)
        alpha = (cv2.GaussianBlur(spot, (0, 0), max(1.0, 0.15 * b)) * (mask > 0))[..., None]
        return np.clip(img * (1 - alpha) + 255 * np.minimum(1.0, alpha * 1.6), 0, 255).astype(np.uint8)
    if kind in ("dark", "bright"):
        return np.clip(img.astype(np.float32) * float(arg.lstrip("x")), 0, 255).astype(np.uint8)
    if kind == "empty":  # the turntable with nothing on it: the backdrop (and its shading) carried on where the item was
        hole = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
        scale = min(1.0, 256 / max(img.shape[:2]))  # inpaint small, then bring the filled backdrop up to size
        small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        small_hole = cv2.resize(hole, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
        filled = cv2.resize(cv2.inpaint(small, small_hole, 7, cv2.INPAINT_TELEA), (img.shape[1], img.shape[0]),
                            interpolation=cv2.INTER_LINEAR)
        noise = np.random.default_rng(0).normal(0, 2.0, img.shape)
        out = img.copy()
        out[hole > 0] = np.clip(filled.astype(np.float32) + noise, 0, 255).astype(np.uint8)[hole > 0]
        return out
    if kind == "cut":  # slide the item off the right edge until this share of it is outside
        x, y, w, h = cv2.boundingRect(mask)
        dx = img.shape[1] - (x + w) + int(float(arg.rstrip("%")) / 100 * w)
        return cv2.warpAffine(img, np.float32([[1, 0, dx], [0, 1, 0]]), (img.shape[1], img.shape[0]),
                              borderMode=cv2.BORDER_REPLICATE)
    raise ValueError(cond)


def spoil(img: np.ndarray, cond: str) -> np.ndarray:
    return degrade(img, segment_fruit(img).mask, cond)


def with_fault(ref: str, cond: str | None) -> str:
    return f"{ref}#{cond}" if cond else ref


def split_ref(ref: str) -> tuple[str, str | None]:
    """'tr6:<file>#motion 17' -> ('tr6:<file>', 'motion 17'); unknown faults are refused."""
    base, sep, cond = ref.partition("#")
    if not sep:
        return ref, None
    if cond not in FAULTS:
        raise ValueError(f"unknown fault {cond!r}")
    return base, cond


class FaultyTurntable:
    """A turntable whose camera spoils the photos at some angles ("every" for all of them, "top" for overhead)."""

    def __init__(self, inner, faults: dict):
        self.inner, self.faults = inner, faults

    def __getattr__(self, name):  # rotate_to, azimuth, moves...: the real turntable's
        return getattr(self.inner, name)

    def _spoiled(self, capture: Capture, cond: str | None) -> Capture:
        if not cond:
            return capture
        return Capture(spoil(capture.image, cond), capture.azimuth, capture.elevation, with_fault(capture.source, cond))

    def capture(self) -> Capture:
        c = self.inner.capture()
        return self._spoiled(c, self.faults.get(round(c.azimuth, 1), self.faults.get("every")))

    def capture_top(self) -> Capture:
        return self._spoiled(self.inner.capture_top(), self.faults.get("top"))

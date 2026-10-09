import os

import cv2
import numpy as np

from chhaant.data.tr6 import Session
from chhaant.decide.camera import TurntableCamera
from chhaant.decide.policy import InspectionPolicy
from chhaant.robot.turntable import VirtualTurntable
from chhaant.vision.model import QualityReading


class BrightnessModel:
    """Stand-in model: a darker item reads as more defective."""

    def predict(self, bgr, mask=None):
        inside = bgr[mask > 0] if mask is not None else bgr.reshape(-1, 3)
        return QualityReading(defect=float(1 - inside.mean() / 255), ripeness=0.5)


def photo(colour):
    img = np.full((240, 180, 3), (228, 226, 224), np.uint8)
    cv2.circle(img, (90, 120), 50, colour, -1)
    return img


def make_session(tmp_path, colours):
    files = []
    for i, colour in enumerate(colours):
        rel = f"tr6_512/Tomato/20250723_1000{i:02d}.jpg"
        os.makedirs(os.path.dirname(tmp_path / rel), exist_ok=True)
        cv2.imwrite(str(tmp_path / rel), photo(colour))
        files.append(rel)
    return Session(fruit="Tomato", date="20250723", day=1, slot=1, files=files, spoiled=0, temp_c=29.0)


def test_policy_drives_the_turntable_and_reads_real_pixels(tmp_path):
    bright = (200, 210, 230)
    session = make_session(tmp_path, [bright] * 17)
    table = VirtualTurntable(session, str(tmp_path))
    verdict = InspectionPolicy().inspect(TurntableCamera(table, BrightnessModel()))
    assert verdict.decision == "clean"
    assert table.moves >= 2
    assert all(s.source.startswith("tr6:") for s in verdict.steps)


def test_dark_side_is_found_and_confirmed(tmp_path):
    bright, rotten = (200, 210, 230), (20, 25, 30)
    colours = [bright] * 17
    for side in (7, 8, 9, 10):  # files 8-11 = side views at 157.5-225 degrees
        colours[side + 1] = rotten
    session = make_session(tmp_path, colours)
    verdict = InspectionPolicy().inspect(TurntableCamera(VirtualTurntable(session, str(tmp_path)), BrightnessModel()))
    assert verdict.decision == "defective"

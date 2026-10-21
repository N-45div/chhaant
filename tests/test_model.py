"""OpenCV 5 must reproduce the PyTorch outputs recorded at export time.

``reference.npz`` holds 32 validation crops and the probabilities PyTorch gave
them in the training kernel. Both OpenCV DNN engines are checked against it.
Skipped when the model has not been downloaded into ``models/``.
"""

import os

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(ROOT, "models", "chhaant_quality_v1.onnx")
REFERENCE = os.path.join(ROOT, "models", "reference.npz")

pytestmark = pytest.mark.skipif(not (os.path.exists(MODEL) and os.path.exists(REFERENCE)),
                                reason="model not downloaded into models/ (python scripts/fetch_model.py)")


@pytest.mark.parametrize("engine", ["new", "classic"])
def test_opencv_matches_pytorch(engine):
    from chhaant.vision.model import QualityModel

    ref = np.load(REFERENCE)
    readings = QualityModel(MODEL, engine).predict_crops(list(ref["crops_bgr"]))
    defect = np.array([r.defect for r in readings])
    ripeness = np.array([r.ripeness for r in readings])
    assert np.abs(defect - ref["defect"]).max() < 1e-3
    assert np.abs(ripeness - ref["ripeness"]).max() < 1e-3


def test_unknown_engine_is_rejected():
    from chhaant.vision.model import QualityModel

    with pytest.raises(ValueError):
        QualityModel(MODEL, "gpu")

"""The learned quality model, run through OpenCV 5's DNN module.

The ONNX graph (trained by ``kaggle/train/train.py``) takes RGB pixels in
0..255, with normalisation inside the graph, and returns two probabilities per
item: ``defect`` (rotten, bruised, damaged) and ``ripeness`` (0 unripe to
1 ripe). OpenCV 5's new graph-based DNN engine runs it on CPU, which is what
the Graviton (COOL) deployment uses; the classic engine is kept as a fallback.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from .crop import MODEL_SIDE, item_crop

ENGINES = {"new": cv2.dnn.ENGINE_NEW, "classic": cv2.dnn.ENGINE_CLASSIC, "auto": cv2.dnn.ENGINE_AUTO}


@dataclass
class QualityReading:
    defect: float    # probability the item is defective
    ripeness: float  # 0 unripe .. 1 fully ripe


class QualityModel:
    def __init__(self, onnx_path: str, engine: str = "new"):
        if engine not in ENGINES:
            raise ValueError(f"engine must be one of {sorted(ENGINES)}")
        self.engine = engine
        self.net = cv2.dnn.readNetFromONNX(onnx_path, ENGINES[engine])

    def predict_crops(self, crops_bgr: list[np.ndarray]) -> list[QualityReading]:
        """Score ready-made model crops (see ``chhaant.vision.crop.item_crop``)."""
        if not crops_bgr:
            return []
        blob = cv2.dnn.blobFromImages(list(crops_bgr), 1.0, (MODEL_SIDE, MODEL_SIDE), swapRB=True)
        self.net.setInput(blob)
        defect, ripeness = self.net.forward(["defect", "ripeness"])
        return [QualityReading(float(d), float(r)) for d, r in zip(defect[:, 0], ripeness[:, 0])]

    def predict(self, bgr: np.ndarray, mask: np.ndarray | None = None) -> QualityReading:
        """Crop the item out of a photo and score it."""
        return self.predict_crops([item_crop(bgr, mask)])[0]

"""Inspection backends: each produce type uses only the capability measured for it.

* TR-6 produce: rotate-until-sure on the recorded 16-angle photos with the
  OpenCV 5 quality model (12% wrong calls leave-one-fruit-out, uncertain items
  handed to a person). No shelf-life number: none was validated for them.
* Avocado: the validated shelf-life forecaster on the two side photos. Defect
  inspection is not offered: a ripe Hass avocado turns near-black, which the
  defect model was never validated on.
"""

import os

import cv2

from chhaant.decide.camera import TurntableCamera
from chhaant.decide.policy import InspectionPolicy, PolicyConfig
from chhaant.decide.shelf import ShelfLife, measure
from chhaant.robot.turntable import VirtualTurntable

# Leave-one-fruit-out thresholds from eval/rotate_until_sure.py (most folds picked these).
TR6_POLICY = PolicyConfig(t_defect=0.7, t_clean=0.1)


class CellInspectors:
    def __init__(self, quality_model, tr6_root: str, avocado_root: str, shelf: ShelfLife, policy: PolicyConfig = TR6_POLICY):
        self.model = quality_model
        self.tr6_root, self.avocado_root = tr6_root, avocado_root
        self.shelf = shelf
        self.policy = policy

    def inspect(self, item) -> dict:
        return self._tr6(item) if item.kind == "tr6" else self._avocado(item)

    def _tr6(self, item) -> dict:
        camera = TurntableCamera(VirtualTurntable(item.session, self.tr6_root), self.model)
        v = InspectionPolicy(self.policy).inspect(camera)
        return {
            "capability": "rotate-until-sure defect inspection (validated on TR-6); no shelf-life number for this produce",
            "verdict": v.decision, "defect_score": round(v.score, 3), "coverage": round(v.coverage, 3),
            "unseen_share": round(1 - v.coverage, 3), "side_views": v.side_views,
            "ripeness": round(v.ripeness, 3), "forecast": None, "reason": v.reason,
            "looks": [{"azimuth": s.azimuth, "defect": round(s.p_defect, 3), "ripeness": round(s.p_ripeness, 3),
                       "why": s.why, "photo": s.source} for s in v.steps],
        }

    def _avocado(self, item) -> dict:
        photos = []
        for rel in item.photos:
            img = cv2.imread(os.path.join(self.avocado_root, rel))
            photos.append(None if img is None else measure(img, self.model))
        forecast = self.shelf.estimate(item.produce, photos, item.temp_c)
        usable = [p for p in photos if p is not None]
        return {
            "capability": "shelf-life forecast (validated: 1.05-day error on 426 held-out avocados); defect inspection not validated for avocado",
            "verdict": "clean" if forecast is not None else "escalate",
            "forecast": forecast, "side_views": len(usable), "coverage": None, "unseen_share": None,
            "ripeness": round(sum(p["p_ripeness"] for p in usable) / len(usable), 3) if usable else None,
            "reason": "forecast from both sides" if forecast else "photos could not be measured",
            "looks": [{"photo": f"avocado:{rel}", "ripeness": None if p is None else round(p["p_ripeness"], 3)}
                      for rel, p in zip(item.photos, photos)],
        }

    def look(self, item, azimuth: float) -> dict:
        if item.kind != "tr6":
            raise ValueError("only 16-angle items can be turned to a chosen angle")
        look = TurntableCamera(VirtualTurntable(item.session, self.tr6_root), self.model).look_at(azimuth)
        return {"azimuth": look.azimuth, "defect": round(look.p_defect, 3), "ripeness": round(look.p_ripeness, 3),
                "photo": look.source}

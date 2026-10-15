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
from chhaant.vision.capture import check_capture

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
            "ripeness": None if v.ripeness is None else round(v.ripeness, 3), "forecast": None, "reason": v.reason,
            "unusable_photos": sum(1 for s in v.steps if s.problem),
            "looks": [_look(s.azimuth, s.p_defect, s.p_ripeness, s.source, s.problem, why=s.why) for s in v.steps],
        }

    def _avocado(self, item) -> dict:
        photos, problems = [], []
        for rel in item.photos:
            img = cv2.imread(os.path.join(self.avocado_root, rel))
            check = None if img is None else check_capture(img)
            problems.append("could not read the photo" if img is None else check.summary)
            photos.append(measure(img, self.model) if check is not None and check.ok else None)
        forecast = self.shelf.estimate(item.produce, photos, item.temp_c)
        usable = [p for p in photos if p is not None]
        bad = [f"side {i + 1}: {pr}" for i, pr in enumerate(problems) if pr]
        return {
            "capability": "shelf-life forecast (validated: 1.05-day error on 426 held-out avocados); defect inspection not validated for avocado",
            "verdict": "clean" if forecast is not None else "escalate",
            "forecast": forecast, "side_views": len(usable), "coverage": None, "unseen_share": None,
            "ripeness": None,
            "reason": (("forecast from both sides" if len(usable) == len(photos) else f"forecast from {len(usable)} side(s)")
                       if forecast else "no usable photo") + (f"; unusable: {'; '.join(bad)}" if bad else ""),
            "unusable_photos": len(bad),
            # the per-photo model readings feed the forecast but are not shown: they were never validated on avocado
            "looks": [{"photo": f"avocado:{rel}", "measured": p is not None, **({"problem": pr} if pr else {})}
                      for rel, p, pr in zip(item.photos, photos, problems)],
        }

    def look(self, item, azimuth: float) -> dict:
        if item.kind != "tr6":
            raise ValueError("only 16-angle items can be turned to a chosen angle")
        look = TurntableCamera(VirtualTurntable(item.session, self.tr6_root), self.model).look_at(azimuth)
        return _look(look.azimuth, look.p_defect, look.p_ripeness, look.source, look.problem)


def _look(azimuth, p_defect, p_ripeness, photo, problem="", **extra) -> dict:
    """One look as the agent sees it: a failed capture shows its problem, never a score."""
    out = {"azimuth": azimuth, "defect": None if problem else round(p_defect, 3),
           "ripeness": None if problem else round(p_ripeness, 3), **extra, "photo": photo}
    if problem:
        out["problem"] = problem
    return out

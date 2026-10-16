"""Inspection backends: each produce type uses only the capability measured for it.

* TR-6 produce: rotate-until-sure on the recorded 16-angle photos with the
  OpenCV 5 quality model (12% wrong calls leave-one-fruit-out, uncertain items
  handed to a person). No shelf-life number: none was validated for them.
  A verdict is acted on alone only where validation says it can be: a "clean"
  call for a produce whose spoiled items it missed more than 10% of the time,
  or a "defective" call where it wrongly rejected more than 10% of fresh ones,
  goes to a person with the measured reason (eval/results/rotate_until_sure.csv).
  Tomato: it missed 10 of 10 spoiled; banana: it rejected 9 of 9 fresh.
* Avocado: the validated shelf-life forecaster on the two side photos. Defect
  inspection is not offered: a ripe Hass avocado turns near-black, which the
  defect model was never validated on.
"""

import copy
import csv
import os

import cv2

from chhaant.decide.camera import TurntableCamera
from chhaant.decide.policy import InspectionPolicy, PolicyConfig
from chhaant.decide.shelf import ShelfLife, measure
from chhaant.robot.faults import FaultyTurntable, spoil, with_fault
from chhaant.robot.turntable import VirtualTurntable
from chhaant.vision.capture import check_capture

# Leave-one-fruit-out thresholds from eval/rotate_until_sure.py (most folds picked these).
TR6_POLICY = PolicyConfig(t_defect=0.7, t_clean=0.1)
VALIDATION = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "eval", "results", "rotate_until_sure.csv")
MAX_MISSED, MAX_FALSE_REJECTS = 0.10, 0.10  # of spoiled items called clean / of fresh items called defective


def load_validation(path: str = VALIDATION) -> dict[str, dict]:
    """Per produce, how rotate-until-sure did on held-out fruit (leave-one-fruit-out)."""
    out = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["system"] == "rotate_until_sure" and r["fruit"] != "ALL":
                spoiled = int(r["spoiled"])
                out[r["fruit"]] = {"spoiled": spoiled, "fresh": int(r["sessions"]) - spoiled,
                                   "missed": int(r["missed_spoiled"]), "false_rejects": int(r["false_rejects"])}
    return out


def gate(produce: str, decision: str, reason: str, validation: dict) -> tuple[str, str]:
    """The verdict the cell may act on alone, or "escalate" with the measured reason it may not."""
    v = validation.get(produce)
    name = produce.replace("_", " ").lower()
    if decision == "clean" and (v is None or not v["spoiled"] or v["missed"] / v["spoiled"] > MAX_MISSED):
        why = "never validated" if v is None or not v["spoiled"] else f"missed {v['missed']} of {v['spoiled']} spoiled ones"
        return "escalate", f"{reason}. A person confirms: for {name} this inspection {why} in validation"
    if decision == "defective" and (v is None or not v["fresh"] or v["false_rejects"] / v["fresh"] > MAX_FALSE_REJECTS):
        why = "never validated" if v is None or not v["fresh"] else f"wrongly rejected {v['false_rejects']} of {v['fresh']} fresh ones"
        return "escalate", f"{reason}. A person confirms before discarding: for {name} this inspection {why} in validation"
    return decision, reason


class CellInspectors:
    def __init__(self, quality_model, tr6_root: str, avocado_root: str, shelf: ShelfLife, policy: PolicyConfig = TR6_POLICY):
        self.model = quality_model
        self.tr6_root, self.avocado_root = tr6_root, avocado_root
        self.shelf = shelf
        self.policy = policy
        self.faults: dict = {}  # item_id -> {angle | "every" | "top" | photo index: fault}; see chhaant.robot.faults
        self.validation = load_validation()

    def with_faults(self, faults: dict) -> "CellInspectors":
        """The same inspectors, with simulated camera faults for some items (one run's copy)."""
        out = copy.copy(self)
        out.faults = faults
        return out

    def _turntable(self, item):
        table = VirtualTurntable(item.session, self.tr6_root)
        return FaultyTurntable(table, self.faults[item.item_id]) if item.item_id in self.faults else table

    def inspect(self, item) -> dict:
        return self._tr6(item) if item.kind == "tr6" else self._avocado(item)

    def _tr6(self, item) -> dict:
        camera = TurntableCamera(self._turntable(item), self.model)
        v = InspectionPolicy(self.policy).inspect(camera)
        verdict, reason = gate(item.produce, v.decision, v.reason, self.validation)
        val = self.validation.get(item.produce)
        measured = (f"validated on held-out {item.produce.replace('_', ' ').lower()}: missed {val['missed']} of "
                    f"{val['spoiled']} spoiled, wrongly rejected {val['false_rejects']} of {val['fresh']} fresh") if val else "not validated"
        return {
            "capability": f"rotate-until-sure defect inspection ({measured}); no shelf-life number for this produce",
            "verdict": verdict, "vision_verdict": v.decision, "defect_score": round(v.score, 3),
            "coverage": round(v.coverage, 3), "unseen_share": round(1 - v.coverage, 3), "side_views": v.side_views,
            "ripeness": None if v.ripeness is None else round(v.ripeness, 3), "forecast": None, "reason": reason,
            "unusable_photos": sum(1 for s in v.steps if s.problem),
            "looks": [_look(s.azimuth, s.p_defect, s.p_ripeness, s.source, s.problem, why=s.why) for s in v.steps],
        }

    def _avocado(self, item) -> dict:
        photos, problems, refs = [], [], []
        for i, rel in enumerate(item.photos):
            img = cv2.imread(os.path.join(self.avocado_root, rel))
            fault = self.faults.get(item.item_id, {}).get(i)
            if img is not None and fault:
                img = spoil(img, fault)
            refs.append(with_fault(f"avocado:{rel}", fault))
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
            "looks": [{"photo": ref, "measured": p is not None, **({"problem": pr} if pr else {})}
                      for ref, p, pr in zip(refs, photos, problems)],
        }

    def look(self, item, azimuth: float) -> dict:
        if item.kind != "tr6":
            raise ValueError("only 16-angle items can be turned to a chosen angle")
        look = TurntableCamera(self._turntable(item), self.model).look_at(azimuth)
        return _look(look.azimuth, look.p_defect, look.p_ripeness, look.source, look.problem)


def _look(azimuth, p_defect, p_ripeness, photo, problem="", **extra) -> dict:
    """One look as the agent sees it: a failed capture shows its problem, never a score."""
    out = {"azimuth": azimuth, "defect": None if problem else round(p_defect, 3),
           "ripeness": None if problem else round(p_ripeness, 3), **extra, "photo": photo}
    if problem:
        out["problem"] = problem
    return out

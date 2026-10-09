"""Score every TR-6 view once and cache it, so fusion and policy experiments are instant.

For each photo: the learned model's defect and ripeness probabilities (OpenCV 5
DNN, new engine) and the classical defect-map score. The model never saw TR-6
in training.

Usage:
    python eval/score_views.py --data data/tr6 --model models/chhaant_quality_v1.onnx
"""

import argparse
import csv
import os
import sys

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.data.tr6 import load_sessions  # noqa: E402
from chhaant.vision.color import white_balance_from_background  # noqa: E402
from chhaant.vision.defects import defect_map, summarise  # noqa: E402
from chhaant.vision.model import QualityModel  # noqa: E402
from chhaant.vision.segment import segment_fruit  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/tr6")
    ap.add_argument("--model", default="models/chhaant_quality_v1.onnx")
    ap.add_argument("--out", default="data/tr6_view_scores.csv")  # reproducible cache, kept out of git
    args = ap.parse_args()

    model = QualityModel(args.model, "new")
    rows = []
    for s in load_sessions(args.data):
        session_id = f"{s.fruit}|{s.date}|{s.slot}"
        for view, rel in enumerate(s.files):
            img = cv2.imread(os.path.join(args.data, rel))
            seg = segment_fruit(img)
            reading = model.predict(img, seg.mask if seg.ok else None)
            classical = ""
            if seg.ok:
                balanced = white_balance_from_background(img, seg.mask)
                classical = round(summarise(defect_map(balanced, seg.mask), seg.mask).area_frac, 5)
            rows.append({
                "session": session_id, "fruit": s.fruit, "spoiled": s.spoiled, "view": view,
                "kind": "top" if view == 0 else "side", "azimuth": "" if view == 0 else round(360.0 * (view - 1) / len(s.side_views), 2),
                "p_defect": round(reading.defect, 5), "p_ripeness": round(reading.ripeness, 5),
                "classical_area": classical, "segmented": int(seg.ok), "file": rel,
            })
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print(f"{len(rows)} views from {len({r['session'] for r in rows})} sessions -> {args.out}")


if __name__ == "__main__":
    main()

"""Does the model's ripeness reading track time-to-spoil on TR-6? (No fitting.)

For the four TR-6 fruits whose identity is clean (banana, carrot, guava, mango;
see chhaant/data/tr6.py), each session's median ripeness reading over its
views is compared with the hours left until that fruit's first spoiled session.
A forecaster can only work if this relation is monotone, so the check is a
Spearman rank correlation per fruit, before the fruit spoils. One fruit per
type: these are single trajectories, not population rates.

Usage:
    python eval/ripeness_vs_time_tr6.py --data data/tr6 --scores data/tr6_view_scores.csv
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.data.tr6 import IDENTITY_UNCERTAIN, load_sessions  # noqa: E402


def spearman(a, b) -> float:
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/tr6")
    ap.add_argument("--scores", default="data/tr6_view_scores.csv")
    ap.add_argument("--out", default="eval/results/ripeness_vs_time_tr6.csv")
    args = ap.parse_args()

    views = defaultdict(list)
    with open(args.scores) as fh:
        for r in csv.DictReader(fh):
            views[r["session"]].append((float(r["p_ripeness"]), float(r["p_defect"])))

    rows = []
    for fruit in sorted({s.fruit for s in load_sessions(args.data)} - IDENTITY_UNCERTAIN):
        life = [s for s in load_sessions(args.data) if s.fruit == fruit and s.hours_to_spoiled is not None]
        before = [s for s in life if s.hours_to_spoiled > 0]
        ripe = [float(np.median([v[0] for v in views[f"{s.fruit}|{s.date}|{s.slot}"]])) for s in before]
        defect = [float(np.median([v[1] for v in views[f"{s.fruit}|{s.date}|{s.slot}"]])) for s in before]
        hours = [s.hours_to_spoiled for s in before]
        row = {"fruit": fruit, "sessions_before_spoiling": len(before),
               "spearman_ripeness_vs_hours_left": round(spearman(ripe, hours), 3),
               "spearman_defect_vs_hours_left": round(spearman(defect, hours), 3),
               "ripeness_first": round(ripe[0], 3), "ripeness_last": round(ripe[-1], 3)}
        rows.append(row)
        print(f"{fruit:8s} sessions {len(before):3d}  rho(ripeness, hours left) {row['spearman_ripeness_vs_hours_left']:+.2f}  "
              f"rho(defect, hours left) {row['spearman_defect_vs_hours_left']:+.2f}  ripeness {ripe[0]:.2f} -> {ripe[-1]:.2f}")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)


if __name__ == "__main__":
    main()

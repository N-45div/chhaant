"""Can a shelf-life estimator learned on some produce types forecast another? (No.)

Sessions of TR-6's four clean-identity fruits (banana, carrot, guava, mango)
up to and including their first spoiled session. Inputs: median ripeness and
defect readings over the session's 17 views (cached by eval/score_views.py)
and the session temperature. q10 is fixed at the avocado value (2.66).

Each fruit is predicted by an estimator fitted on the other three, so the
error is for a produce type the estimator has never seen.

Result (Oct 13 2026): it does not transfer. Held-out error was 1.0 days for
carrot but worse than a constant guess for banana and mango, and 13 days for
guava. So the agent gives no shelf-life numbers for TR-6 produce; only the
avocado forecaster (validated on 426 held-out fruit) is used.

Usage:
    python eval/forecast_tr6.py --data data/tr6 --scores data/tr6_view_scores.csv
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.data.tr6 import IDENTITY_UNCERTAIN, load_sessions  # noqa: E402
from chhaant.decide.forecast import fit  # noqa: E402

AVOCADO_Q10 = 2.66  # measured by eval/forecast_avocado.py


def view_features(readings: list[tuple[float, float]]) -> np.ndarray:
    r = np.asarray(readings, float)
    return np.array([[float(np.median(r[:, 0])), float(np.median(r[:, 1]))]])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/tr6")
    ap.add_argument("--scores", default="data/tr6_view_scores.csv")
    ap.add_argument("--out", default="eval/results/forecast_tr6.csv")
    args = ap.parse_args()

    readings = defaultdict(list)
    with open(args.scores) as fh:
        for r in csv.DictReader(fh):
            readings[r["session"]].append((float(r["p_ripeness"]), float(r["p_defect"])))

    rows = []
    for s in load_sessions(args.data):
        if s.fruit in IDENTITY_UNCERTAIN or s.hours_to_spoiled is None or s.temp_c is None:
            continue
        before_or_first = s.hours_to_spoiled > 0 or not any(
            r[0] == s.fruit and r[3] == 0.0 for r in rows)
        if before_or_first:
            rows.append((s.fruit, view_features(readings[f"{s.fruit}|{s.date}|{s.slot}"])[0], s.temp_c, s.hours_to_spoiled / 24))
    fruits = sorted({r[0] for r in rows})
    X = np.array([r[1] for r in rows])
    temps = np.array([r[2] for r in rows])
    y = np.array([r[3] for r in rows])
    who = np.array([r[0] for r in rows])

    out = []
    print(f"sessions: {len(rows)} from {fruits}; q10 fixed at {AVOCADO_Q10}")
    for f in fruits:
        tr, te = who != f, who == f
        m = fit(X[tr], y[tr], temps[tr], q10_grid=(AVOCADO_Q10,))
        pred = m.predict_days(X[te], temps[te])
        base = np.median(y[tr])
        row = {"held_out": f, "sessions": int(te.sum()), "true_days_max": round(float(y[te].max()), 2),
               "mae_days": round(float(np.mean(np.abs(pred - y[te]))), 2),
               "mae_constant_baseline": round(float(np.mean(np.abs(base - y[te]))), 2)}
        out.append(row)
        print(f"  {f:7s} sessions {row['sessions']:3d}  life {row['true_days_max']:5.1f} d  MAE {row['mae_days']:5.2f} d  "
              f"(constant guess {row['mae_constant_baseline']:5.2f} d)")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(out[0]))
        wr.writeheader()
        wr.writerows(out)


if __name__ == "__main__":
    main()

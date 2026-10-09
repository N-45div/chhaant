"""Does "rotate until sure" beat looking at everything, and what does it cost?

Reads the cached per-view scores (eval/score_views.py) and reports:

1. Fusion over all 16 side views: session ROC AUC for max, mean, median, top2
   and neighbourhood agreement, per produce type.
2. The inspection policy, tuned honestly: for each produce type, thresholds are
   picked on the OTHER five types (leave-one-fruit-out) by a cost where a wrong
   call costs 1, a hand-off to a person 0.3 and each side view 0.01, with fresh
   and spoiled sessions weighted equally. Then it runs on the held-out type.
   Baselines on the same held-out sessions: one side view, and all 16 views with
   max or agreement fusion, each at the threshold tuned the same way.

TR-6 follows one fruit per type (see chhaant/data/tr6.py), so a held-out type
is one physical fruit: these are per-fruit trajectories, not population rates.

Usage:
    python eval/rotate_until_sure.py --scores data/tr6_view_scores.csv
"""

import argparse
import csv
import itertools
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.decide.fusion import agreement, fuse  # noqa: E402
from chhaant.decide.policy import InspectionPolicy, Look, PolicyConfig  # noqa: E402

COST_WRONG, COST_ESCALATE, COST_VIEW = 1.0, 0.3, 0.01
T_DEFECT = (0.5, 0.6, 0.7, 0.8, 0.9)
T_CLEAN = (0.1, 0.2, 0.3, 0.4)


class CachedCamera:
    def __init__(self, rows):
        self.top = next((r for r in rows if r["kind"] == "top"), None)
        self.side = {float(r["azimuth"]): r for r in rows if r["kind"] == "side"}

    def look_down(self) -> Look:
        r = self.top
        return Look(0.0, 90.0, float(r["p_defect"]), float(r["p_ripeness"]), r["file"])

    def look_at(self, azimuth: float) -> Look:
        az = min(self.side, key=lambda a: min(abs(a - azimuth), 360 - abs(a - azimuth)))
        r = self.side[az]
        return Look(az, 40.0, float(r["p_defect"]), float(r["p_ripeness"]), r["file"])


def auc(scores, labels) -> float:
    scores, labels = np.asarray(scores, float), np.asarray(labels)
    pos, neg = scores[labels == 1], scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = np.argsort(np.argsort(np.concatenate([pos, neg]))) + 1.0
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def outcome_cost(decision: str, spoiled: int, views: int) -> float:
    if decision == "escalate":
        return COST_ESCALATE + COST_VIEW * views
    wrong = (decision == "defective") != bool(spoiled)
    return COST_WRONG * wrong + COST_VIEW * views


def balanced_mean(values, labels) -> float:
    values, labels = np.asarray(values, float), np.asarray(labels)
    parts = [values[labels == c].mean() for c in (0, 1) if (labels == c).any()]
    return float(np.mean(parts))


def run_policy(sessions, cfg):
    out = []
    for sid, rows, label in sessions:
        v = InspectionPolicy(cfg).inspect(CachedCamera(rows))
        out.append((v.decision, label, v.side_views))
    return out


def run_fixed(sessions, method, threshold, k):
    out = []
    for sid, rows, label in sessions:
        side = sorted((r for r in rows if r["kind"] == "side"), key=lambda r: float(r["azimuth"]))
        if method == "agreement":
            score = agreement({float(r["azimuth"]): float(r["p_defect"]) for r in side[:k]})[0]
        else:
            score = fuse([float(r["p_defect"]) for r in side[:k]], method)
        out.append(("defective" if score >= threshold else "clean", label, k))
    return out


def cost(results) -> float:
    return balanced_mean([outcome_cost(d, y, n) for d, y, n in results], [y for _, y, _ in results])


def summarise(results) -> dict:
    labels = np.array([y for _, y, _ in results])
    decided = [(d, y) for d, y, _ in results if d != "escalate"]
    wrong = [(d == "defective") != bool(y) for d, y in decided]
    missed = sum(1 for d, y in decided if y == 1 and d == "clean")
    false_reject = sum(1 for d, y in decided if y == 0 and d == "defective")
    return {
        "sessions": len(results), "spoiled": int(labels.sum()),
        "wrong_rate": round(float(np.mean(wrong)) if wrong else 0.0, 3),
        "wrong_calls": int(sum(wrong)),
        "wrong_of_all": round(float(sum(wrong)) / len(results), 3),
        "missed_spoiled": missed, "false_rejects": false_reject,
        "escalated": sum(1 for d, _, _ in results if d == "escalate"),
        "mean_views": round(float(np.mean([n for _, _, n in results])), 2),
        "cost": round(cost(results), 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default="data/tr6_view_scores.csv")
    ap.add_argument("--out", default="eval/results/rotate_until_sure.csv")
    args = ap.parse_args()

    by_session = defaultdict(list)
    with open(args.scores) as fh:
        for r in csv.DictReader(fh):
            by_session[r["session"]].append(r)
    sessions = [(sid, rows, int(rows[0]["spoiled"])) for sid, rows in by_session.items()
                if sum(r["kind"] == "side" for r in rows) == 16 and any(r["kind"] == "top" for r in rows)]
    fruits = sorted({rows[0]["fruit"] for _, rows, _ in sessions})

    print("1) Fusion over all 16 side views: session AUC")
    print("   method      " + "  ".join(f[:8].ljust(8) for f in fruits) + "  pooled")
    for method in ("max", "mean", "median", "top2", "agreement"):
        per, pooled_s, pooled_y = [], [], []
        for f in fruits:
            s_f, y_f = [], []
            for _, rows, y in sessions:
                if rows[0]["fruit"] != f:
                    continue
                side = {float(r["azimuth"]): float(r["p_defect"]) for r in rows if r["kind"] == "side"}
                s = agreement(side)[0] if method == "agreement" else fuse(list(side.values()), method)
                s_f.append(s); y_f.append(y)
            per.append(auc(s_f, y_f)); pooled_s += s_f; pooled_y += y_f
        print(f"   {method:10s}  " + "  ".join(f"{a:.3f}   " for a in per) + f"  {auc(pooled_s, pooled_y):.3f}")

    grid = [(td, tc) for td, tc in itertools.product(T_DEFECT, T_CLEAN) if tc < td]
    rows_out, pooled = [], defaultdict(list)
    print("\n2) Leave-one-fruit-out: tuned on the other five, run on the held-out one")
    for f in fruits:
        train = [s for s in sessions if s[1][0]["fruit"] != f]
        test = [s for s in sessions if s[1][0]["fruit"] == f]
        best_cfg = min((PolicyConfig(t_defect=td, t_clean=tc) for td, tc in grid),
                       key=lambda c: cost(run_policy(train, c)))
        systems = {"rotate_until_sure": run_policy(test, best_cfg)}
        for name, method, k in (("one_view", "max", 1), ("all16_max", "max", 16), ("all16_agreement", "agreement", 16)):
            t_best = min(T_DEFECT + T_CLEAN, key=lambda t: cost(run_fixed(train, method, t, k)))
            systems[name] = run_fixed(test, method, t_best, k)
        for name, res in systems.items():
            row = {"fruit": f, "system": name, **summarise(res)}
            if name == "rotate_until_sure":
                row.update({"t_defect": best_cfg.t_defect, "t_clean": best_cfg.t_clean})
            rows_out.append(row)
            pooled[name] += res
        print(f"   {f}: thresholds from the others: defect>={best_cfg.t_defect}, clean<{best_cfg.t_clean}")

    print("\n   system              wrong(decided)  wrong(all)  missed  false-rej  escalated  views  cost")
    for name, res in pooled.items():
        s = summarise(res)
        print(f"   {name:18s}  {s['wrong_rate']:.3f}           {s['wrong_of_all']:.3f}       {s['missed_spoiled']:5d}   "
              f"{s['false_rejects']:7d}   {s['escalated']:7d}    {s['mean_views']:5.2f}  {s['cost']:.3f}")
        rows_out.append({"fruit": "ALL", "system": name, **s})

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fields = sorted({k for r in rows_out for k in r}, key=lambda k: list(rows_out[0]).index(k) if k in rows_out[0] else 99)
    with open(args.out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields)
        wr.writeheader()
        wr.writerows(rows_out)


if __name__ == "__main__":
    main()

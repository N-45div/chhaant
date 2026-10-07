"""How many views does a spoiled/fresh call need, and does it matter which ones?

Every TR-6 photo gets a classical defect score (share of the item flagged as
defect). A session is then judged from only k of its 16 side views, taking the
worst view (a defect seen anywhere counts). Three ways of choosing the k views:

* consecutive: the first k in shooting order, bunched on one side of the item
* spread: evenly spaced around the item, which is what the coverage map's
  best-next-view picks for a camera circling at a fixed elevation
* random: k random views, averaged over draws

For each k we report the inspected-surface share predicted by the geometry
model and the ROC AUC of the session score against the dataset's spoiled label,
per produce type and pooled. TR-6 follows one fruit per type, so sessions of a
type are not independent; read per-type numbers as trajectories of one fruit.

Usage:
    python eval/views_needed.py --data data/tr6
"""

import argparse
import csv
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.data.tr6 import load_sessions  # noqa: E402
from chhaant.vision.color import white_balance_from_background  # noqa: E402
from chhaant.vision.defects import defect_map, summarise  # noqa: E402
from chhaant.vision.segment import segment_fruit  # noqa: E402
from chhaant.vision.views import CoverageMap  # noqa: E402

SIDE_ELEVATION = 40.0
DRAWS = 30


def score_photo(path: str) -> float:
    img = cv2.imread(path)
    seg = segment_fruit(img)
    if not seg.ok:
        return float("nan")
    balanced = white_balance_from_background(img, seg.mask)
    return summarise(defect_map(balanced, seg.mask), seg.mask).area_frac


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """ROC AUC by ranks (Mann-Whitney U); NaN when only one class is present."""
    pos, neg = scores[labels == 1], scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = np.argsort(np.argsort(np.concatenate([pos, neg]))) + 1.0
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def pick(strategy: str, k: int, n: int, rng: np.random.Generator) -> list[int]:
    if strategy == "consecutive":
        return list(range(k))
    if strategy == "spread":
        return sorted({round(i * n / k) % n for i in range(k)})
    return sorted(rng.choice(n, size=k, replace=False).tolist())


def coverage(indices: list[int], n: int) -> float:
    cov = CoverageMap()
    for i in indices:
        cov.add_view(360.0 * i / n, SIDE_ELEVATION)
    return cov.covered_frac


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/tr6")
    ap.add_argument("--out", default="eval/results/views_needed.csv")
    args = ap.parse_args()

    sessions = [s for s in load_sessions(args.data) if len(s.side_views) == 16]
    paths = [os.path.join(args.data, f) for s in sessions for f in s.side_views]
    with ProcessPoolExecutor() as pool:
        flat = list(pool.map(score_photo, paths, chunksize=32))
    per_view = np.array(flat, np.float32).reshape(len(sessions), 16)
    per_view = np.nan_to_num(per_view, nan=0.0)
    labels = np.array([s.spoiled for s in sessions])
    fruits = np.array([s.fruit for s in sessions])

    rng = np.random.default_rng(0)
    rows = []
    for strategy in ("consecutive", "spread", "random"):
        for k in range(1, 17):
            draws = 1 if strategy != "random" else DRAWS
            pooled, by_fruit, covs = [], {f: [] for f in sorted(set(fruits))}, []
            for _ in range(draws):
                idx = pick(strategy, k, 16, rng)
                covs.append(coverage(idx, 16))
                score = per_view[:, idx].max(axis=1)
                pooled.append(auc(score, labels))
                for f in by_fruit:
                    sel = fruits == f
                    by_fruit[f].append(auc(score[sel], labels[sel]))
            row = {"strategy": strategy, "k": k, "coverage": round(float(np.mean(covs)), 3),
                   "auc_pooled": round(float(np.nanmean(pooled)), 3)}
            row.update({f"auc_{f}": round(float(np.nanmean(v)), 3) for f, v in by_fruit.items()})
            rows.append(row)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)

    print(f"sessions: {len(sessions)} ({labels.sum()} spoiled), photos scored: {len(paths)}")
    cols = [c for c in rows[0] if c.startswith("auc_")]
    print("strategy     k  cover  " + "  ".join(c[4:12].ljust(8) for c in cols))
    for r in rows:
        if r["k"] in (1, 2, 4, 8, 16):
            print(f"{r['strategy']:11s} {r['k']:2d}  {r['coverage']:.2f}   " + "  ".join(f"{r[c]:.3f}   " for c in cols))


if __name__ == "__main__":
    main()

# Findings, Oct 7 2026 (classical defect map only, before the learned model):
# * Banana 1.00, carrot ~0.95, guava ~0.8-0.88: rot and blackening are caught.
# * Tomato is INVERTED (~0.1-0.28): TR-6's spoiled tomatoes turn lighter and
#   more orange (L* 41 -> 50) rather than dark, while the stem scar of fresh
#   ones flags ~3% of the surface. That label needs colour or a learned model.
# * Four evenly spread views inspect 0.62 of the surface vs 0.37 for four
#   bunched ones, and match the AUC of all 16 views.

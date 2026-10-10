"""How well does the ripening clock forecast shelf life on fruit it has never seen?

Data: 478 Hass avocados at 10 C, 20 C or room temperature, photographed daily
from two sides until past stage 4 (end of shelf life). Every photo goes through
the robot's own pipeline (segment, backdrop white balance, CIELAB colour, the
OpenCV 5 quality model). The room-temperature group ("Tam") is treated as
20 C: its shelf-life spread is identical to T20's (median 7 days, range 4-9).

Five-fold cross-validation grouped by fruit (no fruit is ever in both the
fitting and the scoring set). Within each training fold, 20% of the fruits are
held back to set the prediction interval. Forecasters compared:

* constant:      median days left in the training rows
* temp_only:     median days left per storage temperature
* vision_blind:  colour + model readings, ignoring temperature (q10 = 1)
* vision_temp:   colour + model readings + fitted q10 (the ripening clock)
* one_side:      vision_temp from one photo (side a) instead of both sides

Rows: one per fruit per day, up to and including the first stage-4 day.
Fruits never graded stage 4 are censored and left out.

Usage:
    python eval/forecast_avocado.py --data data/avocado --model models/chhaant_quality_v1.onnx
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.data.avocado import load_photos  # noqa: E402
from chhaant.decide.forecast import FEATURES, calibrate_interval, feature_vector, fit  # noqa: E402
from chhaant.vision.color import colour_stats, white_balance_from_background  # noqa: E402
from chhaant.vision.model import QualityModel  # noqa: E402
from chhaant.vision.segment import segment_fruit  # noqa: E402

TEMP_C = {"T10": 10.0, "T20": 20.0, "Tam": 20.0}
FOLDS = 5


def photo_features(path: str, model: QualityModel) -> dict | None:
    img = cv2.imread(path)
    if img is None:
        return None
    seg = segment_fruit(img)
    if not seg.ok:
        return None
    balanced = white_balance_from_background(img, seg.mask)
    st = colour_stats(balanced, seg.mask)
    reading = model.predict(img, seg.mask)
    return dict(L=st.L, a=st.a, b=st.b, hue_deg=st.hue_deg, chroma=st.chroma, dark_frac=st.dark_frac,
                p_ripeness=reading.ripeness, p_defect=reading.defect)


def load_or_build_features(data: str, model_path: str, cache: str) -> dict[str, dict]:
    if os.path.exists(cache):
        with open(cache) as fh:
            return {r["file"]: {k: float(v) for k, v in r.items() if k != "file"} for r in csv.DictReader(fh)}
    model = QualityModel(model_path, "new")
    out = {}
    photos = load_photos(data)
    for n, p in enumerate(photos, 1):
        f = photo_features(os.path.join(data, p.file), model)
        if f is not None:
            out[p.file] = f
        if n % 2000 == 0:
            print(f"features: {n}/{len(photos)}", flush=True)
    with open(cache, "w", newline="") as fh:
        keys = ["file", *next(iter(out.values())).keys()]
        wr = csv.DictWriter(fh, fieldnames=keys)
        wr.writeheader()
        for file, f in out.items():
            wr.writerow({"file": file, **f})
    return out


def fruit_day_rows(photos, feats, sides: tuple[str, ...]):
    """One row per fruit per day: features averaged over the requested sides."""
    groups = defaultdict(list)
    for p in photos:
        if p.days_left is None or p.side not in sides or p.file not in feats:
            continue
        groups[(p.fruit_id, p.day)].append(p)
    rows = []
    for (fruit, day), ps in groups.items():
        first_end = day + ps[0].days_left
        if day > first_end:
            continue
        x = np.mean([feature_vector(feats[p.file]) for p in ps], axis=0)
        rows.append((fruit, ps[0].group, x, float(ps[0].days_left)))
    return rows


def folds_of(fruits: list[str], k: int, seed: int = 0) -> dict[str, int]:
    order = np.random.default_rng(seed).permutation(sorted(fruits))
    return {f: i % k for i, f in enumerate(order)}


def evaluate(rows, fold_of):
    X = np.array([r[2] for r in rows])
    y = np.array([r[3] for r in rows])
    groups = np.array([r[1] for r in rows])
    temps = np.array([TEMP_C[g] for g in groups])
    fruit = np.array([r[0] for r in rows])
    fold = np.array([fold_of[f] for f in fruit])
    preds = {k: np.zeros(len(y)) for k in ("constant", "temp_only", "vision_blind", "vision_temp")}
    lo, hi, q10s = np.zeros(len(y)), np.zeros(len(y)), []
    for k in range(FOLDS):
        tr, te = fold != k, fold == k
        preds["constant"][te] = np.median(y[tr])
        for g in set(groups):
            preds["temp_only"][te & (groups == g)] = np.median(y[tr & (groups == g)])
        blind = fit(X[tr], y[tr], temps[tr], q10_grid=(1.0,))
        preds["vision_blind"][te] = blind.predict_days(X[te], temps[te])
        # interval: fit on 80% of the training fruits, calibrate on the other 20%
        tr_fruits = sorted(set(fruit[tr]))
        cal_set = set(np.random.default_rng(k).choice(tr_fruits, size=len(tr_fruits) // 5, replace=False))
        cal = tr & np.isin(fruit, list(cal_set))
        core = tr & ~cal
        clock = fit(X[core], y[core], temps[core])
        calibrate_interval(clock, X[cal], y[cal], temps[cal])
        clock_full = fit(X[tr], y[tr], temps[tr])
        clock_full.resid_lo, clock_full.resid_hi = clock.resid_lo, clock.resid_hi
        preds["vision_temp"][te] = clock_full.predict_days(X[te], temps[te])
        for i in np.where(te)[0]:
            f = clock_full.predict(X[i:i + 1], temps[i])
            lo[i], hi[i] = f.low, f.high
        q10s.append(clock_full.q10)
    return y, groups, preds, lo, hi, q10s


def mae(p, y):
    return float(np.mean(np.abs(p - y)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/avocado")
    ap.add_argument("--model", default="models/chhaant_quality_v1.onnx")
    ap.add_argument("--cache", default="data/avocado_features.csv")
    ap.add_argument("--out", default="eval/results/forecast_avocado.csv")
    args = ap.parse_args()

    photos = load_photos(args.data)
    feats = load_or_build_features(args.data, args.model, args.cache)
    print(f"photos with features: {len(feats)}/{len(photos)}")

    both = fruit_day_rows(photos, feats, ("a", "b"))
    one = fruit_day_rows(photos, feats, ("a",))
    fold_of = folds_of(sorted({r[0] for r in both}), FOLDS)
    y, groups, preds, lo, hi, q10s = evaluate(both, fold_of)
    y1, _, preds1, _, _, _ = evaluate(one, fold_of)
    preds["one_side"], y_one = preds1["vision_temp"], y1

    out = []
    print(f"fruits: {len(fold_of)}, fruit-days: {len(y)}, q10 per fold: {[round(q, 1) for q in q10s]}")
    print("forecaster      MAE days  T10    T20    Tam    within 1 day")
    for name, p in preds.items():
        yy = y_one if name == "one_side" else y
        gg = groups if name != "one_side" else np.array([r[1] for r in one])
        per = {g: mae(p[gg == g], yy[gg == g]) for g in ("T10", "T20", "Tam")}
        row = {"forecaster": name, "mae_days": round(mae(p, yy), 3), **{f"mae_{g}": round(v, 3) for g, v in per.items()},
               "within_1_day": round(float(np.mean(np.abs(p - yy) <= 1.0)), 3)}
        out.append(row)
        print(f"{name:14s}  {row['mae_days']:6.2f}   {per['T10']:5.2f}  {per['T20']:5.2f}  {per['Tam']:5.2f}   {row['within_1_day']:.2f}")
    coverage = float(np.mean((y >= lo - 1e-6) & (y <= hi + 1e-6)))
    print(f"80% interval coverage on held-out fruit: {coverage:.2f}; fitted q10 {np.mean(q10s):.2f} +/- {np.std(q10s):.2f}")
    out.append({"forecaster": "vision_temp_interval80", "coverage": round(coverage, 3),
                "q10_mean": round(float(np.mean(q10s)), 3), "q10_sd": round(float(np.std(q10s)), 3)})

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fields = list(dict.fromkeys(k for r in out for k in r))
    with open(args.out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields)
        wr.writeheader()
        wr.writerows(out)


if __name__ == "__main__":
    main()

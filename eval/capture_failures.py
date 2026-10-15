"""Bad captures: how often they would mislead the cell, and whether the capture checks catch them.

1. Real photos: TR-6 sessions (512 px) and Hass avocados (800 px), split by
   fruit into a calibration half and a held-out half.
2. Each photo is also degraded the ways a real cell fails: defocus and motion
   blur, a blown-out highlight (glare), under- and over-exposure, an empty
   turntable, and the item cut off by the frame edge.
3. Thresholds for ``chhaant.vision.capture`` come from the calibration half's
   clean photos only: 0.5th / 99.5th percentiles, so about 1% of good photos
   may be flagged. The held-out half then gives the false-alarm rate on good
   photos and the detection rate per failure.
4. Harm without the checks: how far each failure moves the quality model's
   defect score, and how often it changes the view's call (defect >= 0.7,
   clean < 0.1, else unsure), most of all into "clean".

    python eval/capture_failures.py            # eval/results/capture_failures.md (+ .json, _samples.json.gz, _gallery.jpg)
    python eval/capture_failures.py --rescore  # new rules on the saved samples, no images needed

It is heavy (each photo is segmented 12 times): run it with deploy/eval_job.sh.
"""

import argparse
import csv
import gzip
import hashlib
import json
import os
import sys
from multiprocessing import get_context

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.robot.faults import FAULTS, degrade  # noqa: E402
from chhaant.vision.capture import THRESHOLDS, capture_metrics, judge  # noqa: E402
from chhaant.vision.model import QualityModel  # noqa: E402
from chhaant.vision.segment import segment_fruit  # noqa: E402

T_DEFECT, T_CLEAN = 0.7, 0.1  # the cell's TR-6 view thresholds
CONDITIONS = ["clean", *FAULTS]
EXPECTED = {"defocus": "blurred", "motion": "blurred", "glare": "glare", "dark": ("too dark", "no usable item"),
            "bright": ("overexposed", "glare"), "empty": "no usable item", "cut": "cut off"}


def half(key: str) -> str:
    return "calib" if int(hashlib.sha1(key.encode()).hexdigest(), 16) % 2 == 0 else "test"


def photos(tr6_root: str, avocado_root: str, per_split: int) -> list[dict]:
    rows = []
    with open(os.path.join(tr6_root, "tr6_manifest.csv"), newline="") as fh:
        for r in csv.DictReader(fh):
            if r["view"] != "0":  # side views: what the turntable photographs
                rows.append({"path": os.path.join(tr6_root, r["file"]), "set": "TR-6", "spoiled": r["spoiled"] == "1",
                             "split": half(f"{r['fruit']}/{r['date']}/{r['session']}")})
    for name in sorted(os.listdir(avocado_root)):
        if name.lower().endswith(".jpg"):
            group, _, fruit = name.split("_")[:3]
            rows.append({"path": os.path.join(avocado_root, name), "set": "avocado", "spoiled": None,
                         "split": half(f"{group}/{fruit}")})
    picked = []
    for s in ("TR-6", "avocado"):
        for split in ("calib", "test"):
            pool = [r for r in rows if r["set"] == s and r["split"] == split]
            n = per_split if s == "TR-6" else per_split // 2
            picked += pool[::max(1, len(pool) // n)][:n]
    return picked


def call(p: float) -> str:
    return "defect" if p >= T_DEFECT else "clean" if p < T_CLEAN else "unsure"


_MODEL = None


def _init_worker(model_path: str) -> None:
    global _MODEL
    cv2.setNumThreads(1)  # one process per core instead
    _MODEL = QualityModel(model_path)


def measure_photo(r: dict) -> list[dict]:
    img = cv2.imread(r["path"])
    seg = segment_fruit(img)
    if not seg.ok:
        return []  # the clean photo itself is unusable; nothing to degrade
    base = _MODEL.predict(img, seg.mask).defect
    out = []
    for cond in CONDITIONS:
        bad = degrade(img, seg.mask, cond)
        s = segment_fruit(bad)
        m = capture_metrics(bad, s.mask) if s.ok else {}
        p = _MODEL.predict(bad, s.mask if s.ok else None).defect
        out.append({**{k: r[k] for k in ("set", "split", "spoiled")}, "photo": os.path.basename(r["path"]),
                    "condition": cond, "seg_ok": s.ok, "seg_reason": s.reason, "metrics": m,
                    "p_clean": base, "p": p})
    return out


def measure(model_path: str, rows: list[dict], workers: int) -> list[dict]:
    out = []
    # spawn, not fork: a child forked after OpenCV has started its thread pool can hang for good
    with get_context("spawn").Pool(workers, initializer=_init_worker, initargs=(model_path,)) as pool:
        for i, samples in enumerate(pool.imap(measure_photo, rows, chunksize=4)):
            out += samples
            if i % 50 == 0:
                print(f"{i}/{len(rows)} photos", flush=True)
    return out


# ---- calibration and scoring ----------------------------------------------------
def calibrate(samples: list[dict]) -> dict:
    good = [s["metrics"] for s in samples if s["split"] == "calib" and s["condition"] == "clean" and s["metrics"]]
    pct = lambda key, q: float(np.percentile([m[key] for m in good if key in m], q))  # noqa: E731
    # Presence must never reject a real, pale fruit: its bar sits well under the palest good photos
    # (an empty turntable's leftover shadow measures about 10).
    return {"min_contrast": round(0.6 * pct("contrast", 0.5), 1), "min_edge_sharpness": round(pct("edge_sharpness", 0.5), 4), "max_glare": round(max(0.02, pct("glare", 99.5)), 4),
            "min_backdrop_grey": round(pct("backdrop_grey", 0.5), 1),
            "max_item_clipped": round(max(0.05, pct("item_clipped", 99.5)), 4),
            "max_outline_on_edge": round(max(0.02, pct("outline_on_edge", 99.5)), 4)}


def problems(s: dict, t: dict) -> list[str]:
    return [f"no usable item: {s['seg_reason']}"] if not s["seg_ok"] else judge(s["metrics"], t)


def auc(pos: list[float], neg: list[float]) -> float:
    """P(a good photo scores higher than a failed one), ties counted half."""
    pos, neg = np.asarray(pos), np.asarray(neg)
    return float(((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean()))


def report(samples: list[dict], t: dict) -> tuple[str, dict]:
    test = [s for s in samples if s["split"] == "test"]
    lines = ["# Bad captures: harm and detection", "",
             f"Thresholds from {sum(1 for s in samples if s['split'] == 'calib' and s['condition'] == 'clean')} "
             f"calibration photos (0.5th / 99.5th percentiles of good photos):", "",
             "| check | threshold |", "|---|---|"] + [f"| {k} | {v} |" for k, v in t.items()] + [""]
    summary = {"thresholds": t, "conditions": {}}
    head = ["condition", "photos", "flagged", "for the right reason", "median shift in defect score",
            "view call changed", "moved to clean"]
    rows = []
    for cond in CONDITIONS:
        group = [s for s in test if s["condition"] == cond]
        flagged = [s for s in group if problems(s, t)]
        kind = cond.split(" ")[0]
        expected = EXPECTED.get(kind)
        expected = (expected,) if isinstance(expected, str) else expected
        right = [s for s in flagged if expected and any(e in p for p in problems(s, t) for e in expected)]
        shift = [abs(s["p"] - s["p_clean"]) for s in group]
        changed = [s for s in group if call(s["p"]) != call(s["p_clean"])]
        to_clean = [s for s in group if call(s["p"]) == "clean" and call(s["p_clean"]) != "clean"]
        n = max(1, len(group))
        rows.append([cond, len(group), f"{len(flagged) / n:.1%}", "-" if cond == "clean" else f"{len(right) / n:.1%}",
                     f"{np.median(shift):.3f}", f"{len(changed) / n:.1%}", f"{len(to_clean) / n:.1%}"])
        summary["conditions"][cond] = {"photos": len(group), "flagged": len(flagged) / n, "right_reason": len(right) / n,
                                       "median_shift": float(np.median(shift)), "call_changed": len(changed) / n,
                                       "moved_to_clean": len(to_clean) / n}
    lines += ["## Held-out photos", "", "On the clean row, \"flagged\" is the false-alarm rate on good photos.", "",
              "| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    for s_name in ("TR-6", "avocado"):
        g = [s for s in test if s["condition"] == "clean" and s["set"] == s_name]
        lines.append(f"\nFalse alarms on good {s_name} photos: {sum(1 for s in g if problems(s, t))} of {len(g)}.")
    # Safety: a flag on a good photo of a SPOILED fruit would hide the defect behind "bad photo".
    rotten = [s for s in test if s["condition"] == "clean" and s["set"] == "TR-6" and s["spoiled"]]
    fresh = [s for s in test if s["condition"] == "clean" and s["set"] == "TR-6" and s["spoiled"] is False]
    rot_flag, fresh_flag = sum(1 for s in rotten if problems(s, t)), sum(1 for s in fresh if problems(s, t))
    lines.append(f"\nSafety: good photos of spoiled TR-6 fruit flagged {rot_flag} of {len(rotten)} "
                 f"(fresh fruit: {fresh_flag} of {len(fresh)}). A flag here would hide a defect behind \"bad photo\".")
    summary["spoiled_good_flagged"], summary["spoiled_good"] = rot_flag, len(rotten)
    good = [s["metrics"] for s in test if s["condition"] == "clean" and s["metrics"]]
    lines += ["", "## Which blur measure separates sharp from blurred (held-out AUC)", "",
              "| blur | outline sharpness | interior texture |", "|---|---|---|"]
    for cond in ("defocus 1.5", "defocus 3", "motion 9", "motion 17"):
        bad = [s["metrics"] for s in test if s["condition"] == cond and s["metrics"]]
        lines.append(f"| {cond} | {auc([m['edge_sharpness'] for m in good], [m['edge_sharpness'] for m in bad]):.3f} | "
                     f"{auc([m['texture'] for m in good], [m['texture'] for m in bad]):.3f} |")
    spoiled = [s for s in test if s["set"] == "TR-6" and s["spoiled"] and s["condition"] != "clean"]
    hidden = [s for s in spoiled if call(s["p"]) == "clean" and call(s["p_clean"]) != "clean"]
    caught = [s for s in hidden if problems(s, t)]
    lines += ["", f"Spoiled TR-6 views that a failure turned into a \"clean\" call: {len(hidden)} of {len(spoiled)}; "
              f"the checks flag {len(caught)} of those {len(hidden)}."]
    summary["spoiled_hidden"], summary["spoiled_hidden_caught"] = len(hidden), len(caught)
    return "\n".join(lines) + "\n", summary


def gallery(model, path: str, t: dict, out: str) -> None:
    img = cv2.imread(path)
    seg = segment_fruit(img)
    tiles = []
    for cond in CONDITIONS:
        bad = degrade(img, seg.mask, cond)
        s = segment_fruit(bad)
        probs = [f"no item ({s.reason[:22]})"] if not s.ok else judge(capture_metrics(bad, s.mask), t)
        tile = cv2.resize(bad, (192, 256), interpolation=cv2.INTER_AREA)
        tile = cv2.copyMakeBorder(tile, 0, 44, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        colour = (40, 140, 40) if not probs else (40, 40, 200)
        cv2.putText(tile, cond, (6, 274), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1, cv2.LINE_AA)
        cv2.putText(tile, "usable" if not probs else probs[0].split(" (")[0][:26], (6, 292),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, colour, 1, cv2.LINE_AA)
        tiles.append(tile)
    tiles.append(np.full_like(tiles[0], 255))
    grid = np.vstack([np.hstack(tiles[:6]), np.hstack(tiles[6:12])])
    cv2.imwrite(out, grid, [cv2.IMWRITE_JPEG_QUALITY, 85])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tr6", default="data/tr6")
    ap.add_argument("--avocado", default="data/avocado")
    ap.add_argument("--model", default="models/chhaant_quality_v1.onnx")
    ap.add_argument("--per-split", type=int, default=240, help="TR-6 photos per half (avocado: half as many)")
    ap.add_argument("--out", default="eval/results/capture_failures")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--rescore", action="store_true", help="re-run calibration and scoring on the saved samples")
    args = ap.parse_args()
    if args.rescore:
        with gzip.open(args.out + "_samples.json.gz", "rt") as fh:
            samples = json.load(fh)
        t = calibrate(samples)
        text, summary = report(samples, t)
        with open(args.out + ".md", "w", encoding="utf-8") as fh:
            fh.write(text)
        with open(args.out + ".json", "w") as fh:
            json.dump(summary, fh, indent=1)
        print(text)
        return
    samples = measure(args.model, photos(args.tr6, args.avocado, args.per_split), args.workers)
    model = QualityModel(args.model)  # only now: no OpenCV state in the parent while the pool runs
    t = calibrate(samples)
    text, summary = report(samples, t)
    with open(args.out + ".md", "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(args.out + ".json", "w") as fh:
        json.dump(summary, fh, indent=1)
    with gzip.open(args.out + "_samples.json.gz", "wt") as fh:  # every photo x failure, to re-score rule changes
        json.dump(samples, fh)
    tomatoes = sorted(os.listdir(os.path.join(args.tr6, "tr6_512", "Tomato")))
    gallery(model, os.path.join(args.tr6, "tr6_512", "Tomato", tomatoes[len(tomatoes) // 2]), t, args.out + "_gallery.jpg")
    print(text)
    print("current THRESHOLDS in chhaant/vision/capture.py:", THRESHOLDS, "-> calibrated:", t)


if __name__ == "__main__":
    main()

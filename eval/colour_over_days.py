"""Does the colour pipeline track ripening? Run it over every TR-6 photo.

For each photo: segment the item, white-balance against the backdrop, and
measure CIELAB colour. Results are averaged per fruit, day and session, next to
the share of that session's photos the dataset labels as spoiled.

Usage:
    python eval/colour_over_days.py --data data/tr6 --out eval/results/colour_over_days.csv
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.vision.color import colour_stats, white_balance_from_background  # noqa: E402
from chhaant.vision.segment import segment_fruit  # noqa: E402


def measure(args):
    data, row = args
    img = cv2.imread(os.path.join(data, row["file"]))
    seg = segment_fruit(img)
    if not seg.ok:
        return row, None
    balanced = white_balance_from_background(img, seg.mask)
    return row, colour_stats(balanced, seg.mask)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/tr6")
    ap.add_argument("--out", default="eval/results/colour_over_days.csv")
    args = ap.parse_args()

    with open(os.path.join(args.data, "tr6_manifest.csv")) as fh:
        rows = list(csv.DictReader(fh))

    groups, failed = defaultdict(list), 0
    with ProcessPoolExecutor() as pool:
        for row, stats in pool.map(measure, [(args.data, r) for r in rows], chunksize=32):
            if stats is None:
                failed += 1
                continue
            groups[(row["fruit"], int(row["day"]), int(row["session"]))].append((row, stats))

    out_rows = []
    for (fruit, day, session), items in sorted(groups.items()):
        s = [st for _, st in items]
        labels = [int(r["spoiled"]) for r, _ in items if r["spoiled"] != ""]
        out_rows.append({
            "fruit": fruit, "day": day, "session": session, "views": len(items),
            "hue_deg": round(float(np.median([x.hue_deg for x in s])), 2),
            "a_over_b": round(float(np.median([x.a_over_b for x in s])), 3),
            "L": round(float(np.median([x.L for x in s])), 2),
            "chroma": round(float(np.median([x.chroma for x in s])), 2),
            "dark_frac": round(float(np.median([x.dark_frac for x in s])), 4),
            "spoiled_share": round(float(np.mean(labels)), 2) if labels else "",
        })

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
        wr.writeheader()
        wr.writerows(out_rows)

    print(f"photos measured: {sum(len(v) for v in groups.values())}, segmentation refused: {failed}")
    for fruit in sorted({r["fruit"] for r in out_rows}):
        fr = [r for r in out_rows if r["fruit"] == fruit and r["session"] == 1]
        first, last = fr[0], fr[-1]
        print(f"{fruit:18s} session 1, day {first['day']}->{last['day']}: hue {first['hue_deg']:6.1f}->{last['hue_deg']:6.1f}  "
              f"L* {first['L']:5.1f}->{last['L']:5.1f}  dark {first['dark_frac']:.3f}->{last['dark_frac']:.3f}  "
              f"spoiled {first['spoiled_share']}->{last['spoiled_share']}")


if __name__ == "__main__":
    main()

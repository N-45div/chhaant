"""Turn the COOL benchmark reports (eval/bench_cool.py, one per build and machine) into tables.

* the machines and OpenCV builds, as each report recorded them
* each OpenCV call of a look on a 3000 x 4000 camera frame, median ms, with
  COOL's speed-up over the PyPI wheel on the same Graviton4 machine
* whole looks, and what 1,000 inspected items cost at on-demand prices
* whether the builds read every photo the same

Prices: EC2 on-demand Linux in ap-south-1 from the AWS Price List API
(effective 2026-10-01); the COOL software fee from the account's Cost Explorer
($0.05 for 5 instance-hours on Oct 13, $0.04 for 4 on Oct 14).

    python eval/bench_report.py eval/results/bench/<run>
"""

import argparse
import glob
import json
import os

PRICE_PER_HOUR = {"c8g.large": 0.05398, "c7i.large": 0.08925}
COOL_FEE_PER_HOUR = 0.01
LOOKS_PER_ITEM = 3.95  # rotate-until-sure, pooled over TR-6 (eval/rotate_until_sure.py)
CAMERA_LOOK = "look on a camera frame (decode, segment, model)"
ORDER = ["c8g-cool", "c8g-pip", "c7i-pip"]


def load(run_dir: str) -> dict:
    reports = {}
    for p in glob.glob(os.path.join(run_dir, "*bench-*.json")):
        with open(p) as fh:
            r = json.load(fh)
        reports[r["label"]] = r
    return {k: reports[k] for k in sorted(reports, key=lambda k: ORDER.index(k) if k in ORDER else 99)}


def hourly(r: dict) -> float:
    return PRICE_PER_HOUR[r["machine"]["instance_type"]] + (COOL_FEE_PER_HOUR if r["label"].endswith("cool") else 0.0)


def max_reading_gap(a: dict, b: dict) -> dict:
    """Largest difference per reading between two builds, over the same photos."""
    gaps = {}
    for name, ra in a["readings"]["camera_frames"].items():
        for k, v in ra.items():
            gaps[k] = max(gaps.get(k, 0.0), abs(v - b["readings"]["camera_frames"][name][k]))
    for name, (d, rp) in a["readings"]["small_photos"].items():
        d2, r2 = b["readings"]["small_photos"][name]
        gaps["p_defect (512 px)"] = max(gaps.get("p_defect (512 px)", 0.0), abs(d - d2))
        gaps["p_ripeness (512 px)"] = max(gaps.get("p_ripeness (512 px)", 0.0), abs(rp - r2))
    return gaps


def table(head: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def ms(x: float) -> str:
    return f"{x:.1f}" if x >= 10 else f"{x:.2f}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir")
    ap.add_argument("--out", default="eval/results/bench_cool.md")
    args = ap.parse_args()
    reports = load(args.run_dir)
    labels = list(reports)
    parts = [f"# COOL benchmark ({os.path.basename(os.path.normpath(args.run_dir))})", ""]

    parts += ["## Machines and builds", "", table(
        ["run", "instance", "CPU", "OpenCV", "custom HAL", "threads", "numpy"],
        [[k, r["machine"]["instance_type"], r["machine"]["cpu"], r["opencv"]["version"], r["opencv"]["custom_hal"],
          r["opencv"]["threads"], r["opencv"]["numpy"]] for k, r in reports.items()]), ""]

    first = reports[labels[0]]
    frame = "x".join(str(s) for s in first["inputs"]["frame_size"])
    same_box = "c8g-cool" in reports and "c8g-pip" in reports
    head = ["OpenCV call, one look, on a real " + frame + " frame (median ms)"] + labels
    rows = []
    for op in first["frame_ops"]:
        row = [op] + [ms(reports[k]["frame_ops"][op]["median_ms"]) for k in labels]
        if same_box:
            row.append(f"{reports['c8g-pip']['frame_ops'][op]['median_ms'] / reports['c8g-cool']['frame_ops'][op]['median_ms']:.2f}x")
        rows.append(row)
    parts += ["## OpenCV calls", "", table(head + (["COOL vs wheel, same c8g"] if same_box else []), rows), ""]

    rows = []
    for look in first["looks"]:
        rows.append([look] + [ms(reports[k]["looks"][look]["median_ms"]) for k in labels])
    for m in first["model"]:
        rows.append([m] + [ms(reports[k]["model"][m]["median_ms"]) for k in labels])
    parts += ["## Whole looks and the model (median ms)", "", table(["step"] + labels, rows), ""]

    rows = []
    for k, r in reports.items():
        look_ms = r["looks"][CAMERA_LOOK]["median_ms"]
        items_per_hour = 3.6e6 / (look_ms * LOOKS_PER_ITEM)
        rows.append([k, f"${hourly(r):.4f}", ms(look_ms), f"{items_per_hour:,.0f}",
                     f"${hourly(r) / items_per_hour * 1000:.4f}"])
    parts += ["## Cost of inspecting 1,000 items", "",
              f"One process per instance, OpenCV's default threads, {LOOKS_PER_ITEM} camera-frame looks per item "
              "(the rotate-until-sure average). c8g's 2 vCPUs are 2 physical cores; c7i's are 1 core with 2 hyperthreads.",
              "", table(["run", "per hour (EC2 + COOL fee)", "ms per look", "items per hour", "per 1,000 items"], rows), ""]

    if len(labels) > 1:
        rows = []
        for k in labels[1:]:
            gaps = max_reading_gap(reports[labels[0]], reports[k])
            rows.append([f"{labels[0]} vs {k}"] + [f"{gaps[g]:.2g}" for g in sorted(gaps)])
        parts += ["## Same answers?", "", f"Largest difference in any reading, over {first['inputs']['camera_frames']} camera "
                  f"frames and {first['inputs']['small_photos']} 512-px photos.", "",
                  table(["builds"] + sorted(max_reading_gap(reports[labels[0]], reports[labels[1]])), rows), ""]

    text = "\n".join(parts)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()

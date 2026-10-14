"""The COOL benchmark: how fast the cell's own vision runs on one OpenCV build and machine.

Run it once per build (COOL, the PyPI wheel) and per machine (Graviton4 c8g,
Sapphire Rapids c7i); eval/bench_report.py compares the reports. Everything is
timed on real TR-6 photos, and only on calls the cell actually makes:

* frame ops: each OpenCV call of one look, on a full camera frame (3000 x 4000)
* looks: one whole look as the cell runs it (segment -> crop -> quality model)
  on the 512-px photos the deployed app uses, and on full camera frames with
  the JPEG decode included; plus the avocado reading (segment, white balance,
  colour, model) on full frames
* the quality model alone, on each DNN engine

The readings (defect, ripeness, colour per photo) are saved too, so the report
can check that every build gives the same answers, not only different speeds.

    python eval/bench_cool.py --label c8g-cool --out eval/results/bench/c8g-cool.json
"""

import argparse
import glob
import json
import os
import platform
import statistics
import sys
import time
import urllib.request

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.decide.shelf import measure  # noqa: E402
from chhaant.vision.color import lab_image  # noqa: E402
from chhaant.vision.crop import item_crop  # noqa: E402
from chhaant.vision.model import QualityModel  # noqa: E402
from chhaant.vision.segment import WORK_SIDE, segment_fruit  # noqa: E402


def _summary(ts: list[float]) -> dict:
    ts = sorted(ts)
    return {"median_ms": round(statistics.median(ts), 3), "p90_ms": round(ts[int(0.9 * (len(ts) - 1))], 3), "n": len(ts)}


def timed(fn, repeat: int, warmup: int = 2) -> dict:
    for _ in range(warmup):
        fn()
    ts = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1e3)
    return _summary(ts)


def timed_over(inputs: list, fn, repeat: int) -> dict:
    """Median over every input, ``repeat`` passes each (after one warm-up pass on two inputs)."""
    for x in inputs[:2]:
        fn(x)
    ts = []
    for _ in range(repeat):
        for x in inputs:
            t0 = time.perf_counter()
            fn(x)
            ts.append((time.perf_counter() - t0) * 1e3)
    return _summary(ts)


def instance_type() -> str | None:
    """The EC2 instance type from IMDSv2, or None off EC2."""
    try:
        token = urllib.request.urlopen(urllib.request.Request(
            "http://169.254.169.254/latest/api/token", method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"}), timeout=1).read().decode()
        return urllib.request.urlopen(urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-type",
            headers={"X-aws-ec2-metadata-token": token}), timeout=1).read().decode()
    except Exception:
        return None


def cpu_name() -> str:
    try:
        with open("/proc/cpuinfo") as fh:
            info = fh.read()
    except OSError:
        return platform.processor()
    for key in ("model name", "CPU part"):  # x86 names the model; Arm gives a part number (0xd4f = Neoverse V2)
        for line in info.splitlines():
            if line.startswith(key):
                return f"{key}: {line.split(':', 1)[1].strip()}"
    return platform.processor()


def opencv_build() -> dict:
    lines = [l.strip() for l in cv2.getBuildInformation().splitlines()]

    def pick(key):
        return next((l.split(":", 1)[1].strip() for l in lines if l.startswith(key + ":")), None)

    return {"version": cv2.__version__, "file": cv2.__file__, "custom_hal": pick("Custom HAL"),
            "baseline": pick("Baseline"), "dispatched": pick("Dispatched code generation"),
            "parallel": pick("Parallel framework"), "threads": cv2.getNumThreads(), "numpy": np.__version__}


def frame_ops(path: str, repeat: int) -> dict:
    """Each OpenCV call of one look, on one full camera frame."""
    jpeg = np.fromfile(path, np.uint8)
    img = cv2.imdecode(jpeg, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    scale = WORK_SIDE / max(h, w)
    work_size = (round(w * scale), round(h * scale))
    work = cv2.resize(img, work_size, interpolation=cv2.INTER_AREA)
    work_gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    mask = segment_fruit(img).mask
    small_mask = cv2.resize(mask, work_size, interpolation=cv2.INTER_NEAREST)
    k31 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))
    k7 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    ops = {
        "imdecode camera JPEG": lambda: cv2.imdecode(jpeg, cv2.IMREAD_COLOR),
        "resize INTER_AREA to the 512 work size": lambda: cv2.resize(img, work_size, interpolation=cv2.INTER_AREA),
        "cvtColor BGR2GRAY": lambda: cv2.cvtColor(img, cv2.COLOR_BGR2GRAY),
        "cvtColor BGR2Lab, 8-bit": lambda: cv2.cvtColor(img, cv2.COLOR_BGR2Lab),
        "cvtColor BGR2Lab, float (colour stats)": lambda: lab_image(img),
        "GaussianBlur 5x5": lambda: cv2.GaussianBlur(img, (5, 5), 0),
        "dilate mask 31x31 (white balance)": lambda: cv2.dilate(mask, k31),
        "erode mask 7x7 (colour stats)": lambda: cv2.erode(mask, k7),
        "resize mask INTER_NEAREST to full size": lambda: cv2.resize(small_mask, (w, h), interpolation=cv2.INTER_NEAREST),
        "findContours on the full mask": lambda: cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE),
        "item_crop to 224 for the model": lambda: item_crop(img, mask),
        "threshold Otsu at work size": lambda: cv2.threshold(work_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU),
        "imencode JPEG q85 at work size (photo route)": lambda: cv2.imencode(".jpg", work, [cv2.IMWRITE_JPEG_QUALITY, 85]),
    }
    return {name: timed(fn, repeat) for name, fn in ops.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--label", required=True, help="e.g. c8g-cool, c8g-pip, c7i-pip")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tr6", default="data/tr6")
    ap.add_argument("--full", default="data/tr6_full")
    ap.add_argument("--model", default="models/chhaant_quality_v1.onnx")
    ap.add_argument("--photos", type=int, default=48, help="512-px photos to time looks on")
    ap.add_argument("--repeat", type=int, default=20)
    args = ap.parse_args()
    t_start = time.perf_counter()

    frames = sorted(glob.glob(os.path.join(args.full, "*.jpg")))
    small = sorted(glob.glob(os.path.join(args.tr6, "tr6_512", "*", "*.jpg")))
    small = small[::max(1, len(small) // args.photos)][:args.photos]
    if not frames or not small:
        sys.exit("need data/tr6_full (scripts/fetch_tr6_originals.py) and data/tr6/tr6_512")
    jpegs = [np.fromfile(p, np.uint8) for p in frames]
    small_imgs = [cv2.imread(p) for p in small]
    models = {e: QualityModel(args.model, e) for e in ("new", "classic")}
    model = models["new"]

    def look(img):
        seg = segment_fruit(img)
        return model.predict(img, seg.mask if seg.ok else None)

    def camera_look(jpeg):
        return look(cv2.imdecode(jpeg, cv2.IMREAD_COLOR))

    def avocado_reading(jpeg):
        return measure(cv2.imdecode(jpeg, cv2.IMREAD_COLOR), model)

    looks_repeat = max(1, args.repeat // 7)
    looks = {
        "look on a 512-px photo (the deployed app)": timed_over(small_imgs, look, looks_repeat),
        "look on a camera frame (decode, segment, model)": timed_over(jpegs, camera_look, looks_repeat),
        "avocado reading on a camera frame (adds white balance + colour)": timed_over(jpegs, avocado_reading, looks_repeat),
    }
    crop = item_crop(small_imgs[0], segment_fruit(small_imgs[0]).mask)
    dnn = {f"quality model, 1 crop, ENGINE_{e.upper()}": timed(lambda m=m: m.predict_crops([crop]), args.repeat * 2)
           for e, m in models.items()}
    dnn["quality model, batch of 8, ENGINE_NEW"] = timed(lambda: model.predict_crops([crop] * 8), args.repeat)

    readings = {
        "camera_frames": {os.path.basename(p): {k: round(float(v), 5) for k, v in (avocado_reading(j) or {}).items()}
                          for p, j in zip(frames, jpegs)},
        "small_photos": {os.path.relpath(p, args.tr6).replace(os.sep, "/"): [round(r.defect, 5), round(r.ripeness, 5)]
                         for p, r in zip(small, map(look, small_imgs))},
        "engines_agree": max(abs(a.defect - b.defect) for a, b in zip(models["new"].predict_crops([crop] * 2),
                                                                     models["classic"].predict_crops([crop] * 2))),
    }
    report = {
        "label": args.label,
        "machine": {"instance_type": instance_type(), "cpu": cpu_name(), "arch": platform.machine(),
                    "vcpus": os.cpu_count(), "python": platform.python_version()},
        "opencv": opencv_build(),
        "inputs": {"camera_frames": len(frames), "frame_size": list(cv2.imdecode(jpegs[0], cv2.IMREAD_COLOR).shape[:2]),
                   "small_photos": len(small), "repeat": args.repeat},
        "frame_ops": frame_ops(frames[0], args.repeat),
        "looks": looks,
        "model": dnn,
        "readings": readings,
    }
    report["seconds"] = round(time.perf_counter() - t_start, 1)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=1)
    print(json.dumps({k: report[k] for k in ("label", "machine", "opencv", "looks", "seconds")}, indent=1))


if __name__ == "__main__":
    main()

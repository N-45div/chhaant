"""Build the working datasets for Chhaant on Kaggle.

1. TriModal Ripeness 6 (figshare 30783827, CC BY 4.0) is a 20 GB zip. We read
   only the sRGB photos out of it with HTTP range requests, shrink them to
   512 px, and write a manifest that splits them into fruit / day / session /
   view, with the spoiled label and the session temperature.
2. Catalogue every dataset attached to this kernel, so the training code is
   written against the real folder layout.

Outputs (in /kaggle/working): tr6_512/, tr6_manifest.csv, tr6_methane.csv,
inventory.txt
"""

import collections
import csv
import json
import os
import re
import struct
import time
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import cv2
import numpy as np

ARTICLE = 30783827
OUT = "/kaggle/working"
IMG_DIR = os.path.join(OUT, "tr6_512")
MAX_SIDE = 512
SESSION_GAP_S = 90  # photos of one fruit are ~5 s apart; fruits are hours apart


def article_file():
    meta = json.load(urllib.request.urlopen(f"https://api.figshare.com/v2/articles/{ARTICLE}"))
    f = meta["files"][0]
    return f["download_url"], f["size"]


URL, SIZE = article_file()


def fetch(start, end, tries=5):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{end}", "User-Agent": "chhaant-prep"})
            return urllib.request.urlopen(req, timeout=120).read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)


def central_directory():
    tail = fetch(SIZE - 1_000_000, SIZE - 1)
    i = tail.rfind(b"PK\x06\x06")
    cd_size, cd_off = struct.unpack("<QQ", tail[i + 40:i + 56])
    cd = fetch(cd_off, cd_off + cd_size - 1)
    entries, p = [], 0
    while p < len(cd) and cd[p:p + 4] == b"PK\x01\x02":
        method, = struct.unpack("<H", cd[p + 10:p + 12])
        csize, usize = struct.unpack("<II", cd[p + 20:p + 28])
        nl, el, cl = struct.unpack("<HHH", cd[p + 28:p + 34])
        off, = struct.unpack("<I", cd[p + 42:p + 46])
        name = cd[p + 46:p + 46 + nl].decode("utf-8", "replace")
        extra, q = cd[p + 46 + nl:p + 46 + nl + el], 0
        while q + 4 <= len(extra):  # zip64 sizes and offsets live in extra field 0x0001
            hid, hl = struct.unpack("<HH", extra[q:q + 4])
            data, k = extra[q + 4:q + 4 + hl], 0
            if hid == 1:
                if usize == 0xFFFFFFFF:
                    usize, = struct.unpack("<Q", data[k:k + 8]); k += 8
                if csize == 0xFFFFFFFF:
                    csize, = struct.unpack("<Q", data[k:k + 8]); k += 8
                if off == 0xFFFFFFFF:
                    off, = struct.unpack("<Q", data[k:k + 8]); k += 8
            q += 4 + hl
        entries.append({"name": name, "method": method, "csize": csize, "usize": usize, "off": off})
        p += 46 + nl + el + cl
    return entries


def read_entry(e):
    blob = fetch(e["off"], e["off"] + 30 + 2048 + e["csize"])
    lnl, lel = struct.unpack("<HH", blob[26:30])
    start = 30 + lnl + lel
    raw = blob[start:start + e["csize"]]
    return zlib.decompress(raw, -15) if e["method"] == 8 else raw


def shrink(jpeg_bytes):
    img = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_REDUCED_COLOR_2)
    h, w = img.shape[:2]
    s = MAX_SIDE / max(h, w)
    img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return enc.tobytes(), (w * 2, h * 2)


def stamp(fname):
    m = re.match(r"(\d{8})_(\d{6})", fname)
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S") if m else None


def parse_methane(text):
    """Return {(day, case): {"R": mean_ppm, "L": mean_ppm}} from a TR-6 gas log."""
    out, day, case, side = collections.defaultdict(dict), None, None, None
    acc = collections.defaultdict(list)
    for line in text.splitlines():
        line = line.strip()
        if m := re.match(r"Day (\d+)", line):
            day = int(m.group(1))
        elif m := re.match(r"case (\d+)", line):
            case = int(m.group(1))
        elif line in ("R", "L"):
            side = line
        elif (m := re.search(r"Methane: ([\d.]+) ppm", line)) and day and case and side:
            acc[(day, case, side)].append(float(m.group(1)))
    for (d, c, s), vals in acc.items():
        out[(d, c)][s] = round(float(np.mean(vals)), 3)
    return out


def build_tr6():
    os.makedirs(IMG_DIR, exist_ok=True)
    entries = central_directory()
    print("zip entries", len(entries))
    srgb = [e for e in entries if "/Normal/" in e["name"] and "/sRGB_images/" in e["name"] and e["name"].lower().endswith(".jpg")]
    spoiled = {}
    for e in entries:
        m = re.match(r"TR-6/Classified/([^/]+)/(Spoiled|Not_spoiled)/sRGB_images/(.+\.jpg)$", e["name"], re.I)
        if m:
            spoiled[(m.group(1), m.group(3))] = int(m.group(2) == "Spoiled")
    ir_temps = collections.defaultdict(list)  # fruit -> [(time, tmin, tmax)]
    for e in entries:
        m = re.match(r"TR-6/Normal/([^/]+)/IR_fusion_images/(\d{8}_\d{6})_([\d.]+)C_([\d.]+)C\.jpg$", e["name"])
        if m:
            ir_temps[m.group(1)].append((stamp(m.group(2)), float(m.group(3)), float(m.group(4))))

    rows, sizes = [], {}
    with ThreadPoolExecutor(32) as pool:
        futs = {pool.submit(read_entry, e): e for e in srgb}
        for n, fut in enumerate(as_completed(futs), 1):
            e = futs[fut]
            fruit, fname = e["name"].split("/")[2], e["name"].split("/")[-1]
            small, orig = shrink(fut.result())
            os.makedirs(os.path.join(IMG_DIR, fruit), exist_ok=True)
            with open(os.path.join(IMG_DIR, fruit, fname), "wb") as fh:
                fh.write(small)
            sizes[(fruit, fname)] = orig
            if n % 250 == 0:
                print(f"{n}/{len(srgb)} images", flush=True)

    by_fruit = collections.defaultdict(list)
    for fruit, fname in sizes:
        by_fruit[fruit].append(fname)
    for fruit, names in sorted(by_fruit.items()):
        names.sort()
        dates = sorted({n[:8] for n in names})
        for day_idx, date in enumerate(dates, 1):
            day_names = [n for n in names if n.startswith(date)]
            sessions, cur = [], [day_names[0]]
            for a, b in zip(day_names, day_names[1:]):
                if (stamp(b) - stamp(a)).total_seconds() > SESSION_GAP_S:
                    sessions.append(cur); cur = []
                cur.append(b)
            sessions.append(cur)
            for s_idx, sess in enumerate(sessions, 1):
                t0, t1 = stamp(sess[0]), stamp(sess[-1])
                near = [(lo, hi) for t, lo, hi in ir_temps[fruit] if abs((t - t0).total_seconds()) < 3600 or t0 <= t <= t1]
                tmin = round(float(np.mean([x[0] for x in near])), 2) if near else ""
                tmax = round(float(np.mean([x[1] for x in near])), 2) if near else ""
                for v_idx, fname in enumerate(sess):
                    w, h = sizes[(fruit, fname)]
                    rows.append({
                        "fruit": fruit, "file": f"tr6_512/{fruit}/{fname}", "date": date, "day": day_idx,
                        "session": s_idx, "sessions_that_day": len(sessions), "view": v_idx, "views_in_session": len(sess),
                        "spoiled": spoiled.get((fruit, fname), ""), "temp_min_c": tmin, "temp_max_c": tmax,
                        "orig_w": w, "orig_h": h,
                    })
    with open(os.path.join(OUT, "tr6_manifest.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader(); wr.writerows(rows)
    print("manifest rows", len(rows))

    gas_rows = []
    for e in entries:
        m = re.match(r"TR-6/Normal/([^/]+)/Methane_gas_readings\.txt$", e["name"])
        if m:
            for (day, case), sides in sorted(parse_methane(read_entry(e).decode("utf-8", "replace")).items()):
                gas_rows.append({"fruit": m.group(1), "day": day, "case": case, "ppm_R": sides.get("R", ""), "ppm_L": sides.get("L", "")})
    with open(os.path.join(OUT, "tr6_methane.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["fruit", "day", "case", "ppm_R", "ppm_L"])
        wr.writeheader(); wr.writerows(gas_rows)
    print("methane rows", len(gas_rows))

    summary = collections.Counter((r["fruit"], r["views_in_session"]) for r in rows)
    print("views per session, by fruit:", sorted(summary.items()))


def inventory(root="/kaggle/input", max_depth=5):
    lines = []
    for ds in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        base = os.path.join(root, ds)
        lines.append(f"\n##### {base}")
        for dirpath, dirnames, filenames in os.walk(base):
            depth = dirpath[len(base):].count(os.sep)
            if depth > max_depth:
                continue
            exts = collections.Counter(os.path.splitext(f)[1].lower() for f in filenames)
            if filenames:
                lines.append(f"{'  ' * depth}{dirpath[len(base):] or '/'}  files={len(filenames)} {dict(exts)} e.g. {sorted(filenames)[:2]}")
            for f in filenames:
                if f.lower().endswith((".csv", ".txt", ".json", ".yaml", ".yml", ".md", ".xml")) and len(lines) < 4000:
                    try:
                        with open(os.path.join(dirpath, f), errors="replace") as fh:
                            head = fh.read(600).replace("\n", " | ")
                        lines.append(f"{'  ' * depth}  >> {f}: {head}")
                    except OSError:
                        pass
    text = "\n".join(lines)
    with open(os.path.join(OUT, "inventory.txt"), "w") as fh:
        fh.write(text)
    print(text[:20000])


if __name__ == "__main__":
    inventory()
    build_tr6()

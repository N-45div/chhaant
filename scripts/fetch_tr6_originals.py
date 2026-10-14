"""Fetch a few full-size TR-6 photos, as the camera took them (3000 x 4000 sRGB).

The deployed app works from 512-px copies; the COOL benchmark also needs real
camera frames, because a live cell would decode and shrink one per look. Each
photo is one HTTP range read out of the figshare zip (~4 MB).

    python scripts/fetch_tr6_originals.py --out data/tr6_full --per-fruit 2
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kaggle", "prep"))
import prep  # noqa: E402  (reads the zip's size and URL from figshare on import)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="data/tr6_full")
    ap.add_argument("--per-fruit", type=int, default=2)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    srgb = [e for e in prep.central_directory()
            if "/Normal/" in e["name"] and "/sRGB_images/" in e["name"] and e["name"].lower().endswith(".jpg")]
    by_fruit: dict[str, list[dict]] = {}
    for e in sorted(srgb, key=lambda e: e["name"]):
        by_fruit.setdefault(e["name"].split("/")[2], []).append(e)

    for fruit, entries in sorted(by_fruit.items()):
        step = max(1, len(entries) // args.per_fruit)  # spread over the fruit's days, not one session
        for e in entries[::step][:args.per_fruit]:
            path = os.path.join(args.out, f"{fruit}_{e['name'].rsplit('/', 1)[-1]}")
            if os.path.exists(path):
                continue
            (_, data), = prep.read_block([e])
            with open(path, "wb") as fh:
                fh.write(data)
            print(f"{path}  {len(data) / 2**20:.1f} MB", flush=True)


if __name__ == "__main__":
    main()

"""Download the 'Hass' Avocado Ripening Photographic Dataset into data/avocado/.

Mendeley Data 3xd9n945v8 (CC BY 4.0): 478 avocados stored at 10 C, 20 C or
room temperature, photographed daily from two opposite sides until past their
shelf life, with a 1-5 ripening stage per photo and a spreadsheet of metadata.
There is no single archive, so the 14,711 files are fetched one by one, a few
at a time, with back-off on rate limits and a SHA-256 check on each file.

Usage:
    python scripts/fetch_avocado.py --out data/avocado
"""

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

API = "https://data.mendeley.com/public-api/datasets/3xd9n945v8"
UA = {"User-Agent": "chhaant-fetch/0.1 (research download)"}  # Mendeley rejects Python's default agent


def fetch(url: str, tries: int = 8) -> bytes:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=120).read()
        except urllib.error.HTTPError as err:
            if attempt == tries - 1 or err.code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(float(err.headers.get("Retry-After") or 0) or 5 * 2 ** attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == tries - 1:
                raise
            time.sleep(5 * 2 ** attempt)


def download(entry: dict, out: str) -> str:
    path = os.path.join(out, entry["filename"])
    want = entry["content_details"]["sha256_hash"]
    if os.path.exists(path):
        with open(path, "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() == want:
                return "kept"
    data = fetch(entry["content_details"]["download_url"])
    if hashlib.sha256(data).hexdigest() != want:
        raise ValueError(f"checksum mismatch: {entry['filename']}")
    with open(path, "wb") as fh:
        fh.write(data)
    return "new"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/avocado")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    files = json.loads(fetch(API))["files"]
    done, failed = {"kept": 0, "new": 0}, []
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(download, f, args.out): f["filename"] for f in files}
        for n, fut in enumerate(as_completed(futures), 1):
            try:
                done[fut.result()] += 1
            except Exception as err:  # keep going; report at the end
                failed.append((futures[fut], str(err)[:120]))
            if n % 1000 == 0:
                print(f"{n}/{len(files)}", flush=True)
    print(f"{len(files)} files: {done['new']} downloaded, {done['kept']} already present, {len(failed)} failed")
    for name, err in failed[:10]:
        print("  failed:", name, err)


if __name__ == "__main__":
    main()

"""Publish the chhaant package to Kaggle as a private dataset for the kernels.

The GitHub repo is private, so kernels cannot pip-install it. Instead the
package is zipped into the private dataset ``divijio/chhaant-src``; kernels
attach it and import straight from the zip.

Usage:
    python kaggle/publish_src.py "message for this version"
"""

import json
import os
import subprocess
import sys
import tempfile
import zipfile

DATASET = "divijio/chhaant-src"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build(folder: str) -> None:
    with zipfile.ZipFile(os.path.join(folder, "chhaant_src.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, _, files in os.walk(os.path.join(ROOT, "chhaant")):
            for f in files:
                if f.endswith(".py"):
                    full = os.path.join(dirpath, f)
                    z.write(full, os.path.relpath(full, ROOT))
    with open(os.path.join(folder, "dataset-metadata.json"), "w") as fh:
        json.dump({"title": "chhaant-src", "id": DATASET, "licenses": [{"name": "other"}]}, fh)


def main() -> None:
    message = sys.argv[1] if len(sys.argv) > 1 else "update"
    exists = subprocess.run(["kaggle", "datasets", "status", DATASET], capture_output=True, text=True)
    with tempfile.TemporaryDirectory() as folder:
        build(folder)
        if exists.returncode == 0 and "ready" in exists.stdout.lower():
            cmd = ["kaggle", "datasets", "version", "-p", folder, "-m", message]
        else:
            cmd = ["kaggle", "datasets", "create", "-p", folder]
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()

"""Download the SO-101 arm model from MuJoCo Menagerie into assets/so101/.

Only the ``robotstudio_so101`` folder (~19 MB) is fetched, not the whole
Menagerie (~1.9 GB). The files are not committed to this repo; see their own
LICENSE in assets/so101/.

Usage:
    python scripts/fetch_so101.py
"""

import json
import os
import urllib.request

REPO = "google-deepmind/mujoco_menagerie"
FOLDER = "robotstudio_so101"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "assets", "so101")


def main() -> None:
    tree = json.load(urllib.request.urlopen(f"https://api.github.com/repos/{REPO}/git/trees/main?recursive=1"))
    files = [t["path"] for t in tree["tree"] if t["type"] == "blob" and t["path"].startswith(FOLDER + "/")]
    for path in files:
        out = os.path.join(DEST, os.path.relpath(path, FOLDER))
        if os.path.exists(out):
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        urllib.request.urlretrieve(f"https://raw.githubusercontent.com/{REPO}/main/{path}", out)
    print(f"{len(files)} files in {DEST}")


if __name__ == "__main__":
    main()

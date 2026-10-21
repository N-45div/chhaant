"""Download the quality model and its OpenCV-vs-PyTorch reference into models/.

Both come from the repository's ``model-v1`` GitHub Release and are checked
against their SHA-256 before they are kept. ``kaggle/train/train.py`` trains the
same model from the public datasets credited in the README.

Usage:
    python scripts/fetch_model.py
"""

import hashlib
import os
import urllib.request

RELEASE = "https://github.com/N-45div/chhaant/releases/download/model-v1"
FILES = {  # name -> SHA-256
    "chhaant_quality_v1.onnx": "36e0ed93b76bdc9f1b996e2750d32fa9706a9b79b2dc4cd0827bec7bc1f20bb9",
    "reference.npz": "74247f00fb8f8d6e50074a4ed7218d733f0e1bbf5a64453b504fd4b0f1fa830e",
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "models")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    os.makedirs(DEST, exist_ok=True)
    for name, digest in FILES.items():
        out = os.path.join(DEST, name)
        if os.path.exists(out) and sha256(out) == digest:
            continue
        part = out + ".part"
        urllib.request.urlretrieve(f"{RELEASE}/{name}", part)
        if sha256(part) != digest:
            os.remove(part)
            raise SystemExit(f"{name}: checksum mismatch, not kept")
        os.replace(part, out)
    print(f"{len(FILES)} files in {DEST}, checksums verified")


if __name__ == "__main__":
    main()

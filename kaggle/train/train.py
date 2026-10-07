"""Train Chhaant's quality model on a Kaggle GPU and export it to ONNX for OpenCV 5.

One MobileNetV3 backbone, two heads:
  defect   - probability the item is rotten, bruised or otherwise defective
  ripeness - 0 = unripe ... 1 = fully ripe
Each image carries only the labels its dataset provides; the other head's loss
is masked out. Every image goes through the same segment-and-crop step the
robot uses at inference (chhaant.vision.crop.item_crop).

TR-6 is held out entirely: it is the test set for transfer to an unseen camera
and scene, scored locally through OpenCV 5.

Outputs (/kaggle/working): chhaant_quality_v1.onnx, metrics.json,
reference.npz (crops + PyTorch outputs for the OpenCV parity test), parity.json
"""

import glob
import json
import os
import random
import subprocess
import sys
from multiprocessing import Pool

import cv2
import numpy as np
import torch
import torch.nn as nn
import torchvision

OUT = "/kaggle/working"
SEED = 7
EPOCHS = 10
BATCH = 64
VAL_FRAC = 0.15
MAX_SIDE = 1024
MODEL_NAME = "chhaant_quality_v1.onnx"


def find(pattern):
    return sorted(glob.glob("/kaggle/input/**/" + pattern, recursive=True))


def load_chhaant():
    zips = find("chhaant_src.zip")
    if zips:
        sys.path.insert(0, zips[0])
    else:
        sys.path.insert(0, os.path.dirname(os.path.dirname(find("chhaant/__init__.py")[0])))


load_chhaant()
from chhaant.vision.crop import item_crop  # noqa: E402
from chhaant.vision.segment import segment_fruit  # noqa: E402

IMG_EXT = (".jpg", ".jpeg", ".png")


def images(pattern):
    return [p for p in find(pattern) if p.lower().endswith(IMG_EXT)]


def collect():
    """(path, bbox, defect, ripeness, source, split, segment). -1 means 'no label'."""
    s = []
    for cls, d in (("Fresh", 0), ("Rotten", 1)):
        for p in images(f"Tomato Quality Grading Dataset/Original Dataset/{cls}/*"):
            s.append((p, None, d, -1.0, "tomato_quality", None, True))
    for cls, r in (("Immature", 0.0), ("Mature", 1.0)):
        for p in images(f"Tomato Maturity Detection Dataset/Original Dataset/{cls}/*"):
            s.append((p, None, -1, r, "tomato_maturity", None, True))
    for cls in ("unaffected", "unripe", "bruised", "cracked", "rotten", "spotted"):
        d = 0 if cls in ("unaffected", "unripe") else 1
        r = 0.0 if cls == "unripe" else -1.0
        for p in images(f"african_plums/{cls}/*"):
            s.append((p, None, d, r, "plums", None, False))  # already tight crops
    for split in ("training", "validation"):
        for folder in glob.glob(f"/kaggle/input/**/industrial-fruit-defect-detection-conveyor-belt/{split}/*", recursive=True):
            cls = os.path.basename(folder).lower()
            if "buen_estado" in cls:
                d = 0
            elif "danad" in cls:
                d = 1
            else:
                continue  # "Vacio": empty belt
            for p in images(f"industrial-fruit-defect-detection-conveyor-belt/{split}/{os.path.basename(folder)}/*"):
                s.append((p, None, d, -1.0, "conveyor", "train" if split == "training" else "val", True))
    for ann in find("_annotations.coco.json"):
        if "banana" not in ann.lower():
            continue
        coco = json.load(open(ann))
        degree = {c["id"]: int(c["name"][6:]) for c in coco["categories"] if c["name"].startswith("degree")}
        top = max(degree.values())
        files = {im["id"]: os.path.join(os.path.dirname(ann), im["file_name"]) for im in coco["images"]}
        for a in coco["annotations"]:
            if a["category_id"] in degree:
                r = (degree[a["category_id"]] - 1) / (top - 1)
                s.append((files[a["image_id"]], a["bbox"], -1, r, "banana_ripeness", None, True))
    return s


def prepare(sample):
    path, bbox, *_rest, segment = sample
    img = cv2.imread(path)
    if img is None:
        return None
    if bbox is not None:
        x, y, w, h = (int(v) for v in bbox)
        px, py = int(0.15 * w), int(0.15 * h)
        img = img[max(0, y - py):y + h + py, max(0, x - px):x + w + px]
    h, w = img.shape[:2]
    if max(h, w) > MAX_SIDE:
        s = MAX_SIDE / max(h, w)
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    mask = None
    if segment:
        seg = segment_fruit(img)
        mask = seg.mask if seg.ok else None
    return item_crop(img, mask)


def split_samples(samples):
    rng = random.Random(SEED)
    out = []
    for smp in samples:
        split = smp[5] or ("val" if rng.random() < VAL_FRAC else "train")
        out.append(smp[:5] + (split,) + smp[6:])
    return out


class QualityNet(nn.Module):
    """Takes RGB in 0..255 (normalisation is part of the graph), returns logits."""

    def __init__(self):
        super().__init__()
        base = torchvision.models.mobilenet_v3_large(weights="IMAGENET1K_V2")
        self.features = base.features
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.neck = nn.Sequential(nn.Flatten(), nn.Linear(960, 256), nn.Hardswish(), nn.Dropout(0.2))
        self.defect = nn.Linear(256, 1)
        self.ripeness = nn.Linear(256, 1)
        self.register_buffer("mean", torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1))

    def forward(self, x):
        x = (x / 255.0 - self.mean) / self.std
        h = self.neck(self.pool(self.features(x)))
        return self.defect(h), self.ripeness(h)


class Probabilities(nn.Module):
    def __init__(self, net):
        super().__init__()
        self.net = net

    def forward(self, image):
        d, r = self.net(image)
        return torch.sigmoid(d), torch.sigmoid(r)


def to_tensor(bgr_batch, device):
    x = torch.from_numpy(bgr_batch[..., ::-1].copy()).to(device)  # BGR -> RGB
    return x.permute(0, 3, 1, 2).float()


def augment(x):
    if random.random() < 0.5:
        x = torch.flip(x, dims=[3])
    if random.random() < 0.5:
        x = torch.flip(x, dims=[2])
    x = torch.rot90(x, random.randint(0, 3), dims=[2, 3])
    gain = torch.empty(x.shape[0], 1, 1, 1, device=x.device).uniform_(0.9, 1.1)
    bias = torch.empty(x.shape[0], 1, 1, 1, device=x.device).uniform_(-10, 10)
    return (x * gain + bias).clamp(0, 255)


def auc(scores, labels):
    scores, labels = np.asarray(scores), np.asarray(labels)
    pos, neg = scores[labels == 1], scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = np.argsort(np.argsort(np.concatenate([pos, neg]))) + 1.0
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def predict(net, X, device):
    net.eval()
    outs_d, outs_r = [], []
    with torch.no_grad():
        for i in range(0, len(X), 256):
            d, r = net(to_tensor(X[i:i + 256], device))
            outs_d.append(torch.sigmoid(d).float().cpu().numpy()[:, 0])
            outs_r.append(torch.sigmoid(r).float().cpu().numpy()[:, 0])
    return np.concatenate(outs_d), np.concatenate(outs_r)


def evaluate(net, X, D, R, src, device):
    pd_, pr = predict(net, X, device)
    m = {}
    for s in sorted(set(src)):
        sel = src == s
        if (D[sel] >= 0).any():
            dl = D[sel] >= 0
            m[f"{s}/defect_auc"] = auc(pd_[sel][dl], D[sel][dl])
            m[f"{s}/defect_acc"] = float(np.mean((pd_[sel][dl] > 0.5) == (D[sel][dl] == 1)))
        if (R[sel] >= 0).any():
            rl = R[sel] >= 0
            if set(np.unique(R[sel][rl])) <= {0.0, 1.0}:
                m[f"{s}/ripeness_auc"] = auc(pr[sel][rl], (R[sel][rl] > 0.5).astype(int))
            else:
                m[f"{s}/ripeness_spearman"] = spearman(pr[sel][rl], R[sel][rl])
    vals = [v for v in m.values() if not np.isnan(v)]
    m["score"] = float(np.mean([v for k, v in m.items() if k.endswith(("_auc", "_spearman")) and not np.isnan(v)])) if vals else 0.0
    return m


def pick_device():
    if torch.cuda.is_available():
        try:
            torch.zeros(1, device="cuda").add_(1)
            return "cuda"
        except Exception as err:  # e.g. a GPU too old for this torch build
            print("CUDA unusable, training on CPU:", err)
    return "cpu"


def export(net, X_ref):
    net = net.float().cpu().eval()
    wrapped = Probabilities(net).eval()
    dummy = torch.zeros(1, 3, 224, 224)
    kwargs = dict(input_names=["image"], output_names=["defect", "ripeness"], opset_version=17,
                  dynamic_axes={"image": {0: "n"}, "defect": {0: "n"}, "ripeness": {0: "n"}})
    path = os.path.join(OUT, MODEL_NAME)
    try:
        torch.onnx.export(wrapped, dummy, path, dynamo=False, **kwargs)
    except TypeError:
        torch.onnx.export(wrapped, dummy, path, **kwargs)
    with torch.no_grad():
        d, r = wrapped(to_tensor(X_ref, "cpu"))
    np.savez_compressed(os.path.join(OUT, "reference.npz"), crops_bgr=X_ref,
                        defect=d.numpy()[:, 0], ripeness=r.numpy()[:, 0])
    return path


PARITY = r"""
import json, sys, numpy as np
sys.path.insert(0, "/kaggle/working/cv5")
import cv2
ref = np.load("/kaggle/working/reference.npz")
out = {"opencv": cv2.__version__}
for name in ("ENGINE_NEW", "ENGINE_CLASSIC"):
    try:
        net = cv2.dnn.readNetFromONNX("/kaggle/working/MODEL", getattr(cv2.dnn, name))
        blob = cv2.dnn.blobFromImages(list(ref["crops_bgr"]), 1.0, (224, 224), swapRB=True)
        net.setInput(blob)
        d, r = net.forward(["defect", "ripeness"])
        out[name] = {"max_abs_diff_defect": float(np.abs(d[:, 0] - ref["defect"]).max()),
                     "max_abs_diff_ripeness": float(np.abs(r[:, 0] - ref["ripeness"]).max())}
    except Exception as err:
        out[name] = {"error": str(err)[:500]}
json.dump(out, open("/kaggle/working/parity.json", "w"), indent=1)
print(json.dumps(out, indent=1))
""".replace("MODEL", MODEL_NAME)


def parity_check():
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "--target", "/kaggle/working/cv5",
                    "opencv-python-headless==5.0.0.93"], check=False)
    subprocess.run([sys.executable, "-c", PARITY], check=False)
    subprocess.run(["rm", "-rf", "/kaggle/working/cv5"], check=False)


def main():
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    samples = split_samples(collect())
    counts = {}
    for smp in samples:
        counts[(smp[4], smp[5])] = counts.get((smp[4], smp[5]), 0) + 1
    print("samples:", sorted(counts.items()), flush=True)

    with Pool(4) as pool:
        crops = pool.map(prepare, samples, chunksize=16)
    keep = [i for i, c in enumerate(crops) if c is not None]
    print(f"prepared {len(keep)}/{len(samples)} crops", flush=True)
    X = np.stack([crops[i] for i in keep])
    D = np.array([samples[i][2] for i in keep], np.float32)
    R = np.array([samples[i][3] for i in keep], np.float32)
    src = np.array([samples[i][4] for i in keep])
    is_val = np.array([samples[i][5] == "val" for i in keep])
    Xtr, Dtr, Rtr = X[~is_val], D[~is_val], R[~is_val]

    device = pick_device()
    net = QualityNet().to(device)
    pos = max(1.0, float((Dtr == 0).sum()) / max(1.0, float((Dtr == 1).sum())))
    bce_d = nn.BCEWithLogitsLoss(reduction="none", pos_weight=torch.tensor([pos], device=device))
    bce_r = nn.BCEWithLogitsLoss(reduction="none")
    head = [p for n, p in net.named_parameters() if not n.startswith("features")]
    opt = torch.optim.AdamW([{"params": net.features.parameters(), "lr": 3e-4}, {"params": head, "lr": 1e-3}], weight_decay=1e-4)
    steps = EPOCHS * ((len(Xtr) + BATCH - 1) // BATCH)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[3e-4, 1e-3], total_steps=steps)
    scaler = torch.amp.GradScaler(enabled=device == "cuda")

    best, best_state, history = -1.0, None, []
    for epoch in range(EPOCHS):
        net.train()
        order = np.random.permutation(len(Xtr))
        total = 0.0
        for i in range(0, len(order), BATCH):
            idx = order[i:i + BATCH]
            x = augment(to_tensor(Xtr[idx], device))
            d = torch.from_numpy(Dtr[idx]).to(device)
            r = torch.from_numpy(Rtr[idx]).to(device)
            with torch.autocast(device_type=device, enabled=device == "cuda"):
                ld, lr_ = net(x)
            ld, lr_ = ld.float()[:, 0], lr_.float()[:, 0]
            md, mr = (d >= 0).float(), (r >= 0).float()
            loss = (bce_d(ld, d.clamp(min=0)) * md).sum() / md.sum().clamp(min=1) \
                + (bce_r(lr_, r.clamp(min=0)) * mr).sum() / mr.sum().clamp(min=1)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            total += float(loss) * len(idx)
        m = evaluate(net, X[is_val], D[is_val], R[is_val], src[is_val], device)
        m["epoch"], m["train_loss"] = epoch + 1, total / len(Xtr)
        history.append(m)
        print(json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in m.items()}), flush=True)
        if m["score"] > best:
            best, best_state = m["score"], {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}

    net.load_state_dict(best_state)
    ref_idx = np.random.RandomState(SEED).choice(np.where(is_val)[0], size=min(32, int(is_val.sum())), replace=False)
    export(net, X[ref_idx])
    json.dump({"best_score": best, "history": history, "counts": {f"{a}/{b}": n for (a, b), n in counts.items()},
               "device": device, "torch": torch.__version__}, open(os.path.join(OUT, "metrics.json"), "w"), indent=1)
    parity_check()


if __name__ == "__main__":
    main()

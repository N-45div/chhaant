# Chhaant

**A robot that picks produce the way a careful shopper does.** It turns each
tomato over before deciding, rejects the bruised one, and picks for the day
you will actually eat it.

*Chhaant* (छाँट) is Hindi for picking out the best from a pile.

Built for the OpenCV AI Competition 2026 (OpenCV 5 + AWS).

> Status: under active development (build window Aug 26 – Oct 26, 2026).
> This README grows with the code; claims are only made once they are measured.

## Layout

| Path | What it holds |
|---|---|
| `chhaant/` | The Python package: vision, decisions, agent |
| `kaggle/` | Kaggle kernels for data preparation and training |
| `tests/` | Unit tests (`pytest`) |

## Setup

Python 3.12 and OpenCV 5:

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use .venv/bin/activate elsewhere
pip install -r requirements.txt
pytest
```

On AWS Graviton the same code runs on the Cloud-Optimized OpenCV Library (COOL)
build that ships with the COOL AMI, instead of the PyPI wheel.

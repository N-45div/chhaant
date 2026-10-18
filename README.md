# Chhaant

**A robot that picks produce the way a careful shopper does.** It turns each
tomato over before deciding, rejects the bruised one, and picks for the day
you will actually eat it.

*Chhaant* (छाँट) is Hindi for picking out the best from a pile.

Built for the OpenCV AI Competition 2026 (OpenCV 5 + AWS). The technical report is
[docs/REPORT.md](docs/REPORT.md); live at <https://d1lk9oj2so3zh7.cloudfront.net>.

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

## Run the web app

```bash
python kaggle/prep/prep.py         # or download the prep kernel's output into data/tr6
python scripts/fetch_avocado.py    # avocado photos into data/avocado
python -m chhaant.web              # then open http://127.0.0.1:8000
```

The agent runs on Amazon Bedrock by default (AWS credentials with Bedrock
access); set `CHHAANT_BACKEND=nemotron` and `NEBIUS_API_KEY` to run it on NVIDIA
Nemotron through Nebius Token Factory instead. Choose "You, here on this page"
to answer the agent's questions yourself: it waits for your answer.

## Licence

Apache License 2.0 (see [LICENSE](LICENSE)).

## Data and model credits

Nothing below is redistributed in this repository; scripts fetch it from the source.

| What | Source | Licence |
|---|---|---|
| TriModal Ripeness 6 (16-angle daily photos to spoilage) | figshare, doi:10.6084/m9.figshare.30783827 | CC BY 4.0 |
| Tomato maturity and quality grading | Kaggle `sujaykapadnis/tomato-maturity-detection-and-quality-grading` (Sher-e-Bangla Agricultural University) | CC BY 4.0 |
| Banana ripeness (CEAGESP stages) | Kaggle `lucianon/banana-ripeness-dataset` | CC BY 4.0 |
| African plums quality and defects | Kaggle `arnaudfadja/african-plums-quality-and-defect-assessment-data` | CC BY-SA 4.0 |
| Fruit defects on a conveyor belt | Kaggle `josembm/industrial-fruit-defect-detection-conveyor-belt` | CC0 1.0 |
| SO-101 arm model | MuJoCo Menagerie `robotstudio_so101` | Apache 2.0 |

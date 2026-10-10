"""The 'Hass' Avocado Ripening Photographic Dataset as labelled photos.

Mendeley Data 3xd9n945v8 (CC BY 4.0, fetched by scripts/fetch_avocado.py):
478 avocados kept at 10 C (T10), 20 C (T20) or room temperature (Tamb), each
photographed daily from two opposite sides and graded on a 1-5 ripening index.
The sheet spells the room-temperature group "Tam" (the dataset text says Tamb);
its shelf life matches T20 (median 7 days vs 17 at 10 C), so the room was ~20 C.
The dataset defines stage 4 as the end of shelf life.

Each photo gets ``days_left``: days from that photo until its fruit first
reached stage 4 (0 on and after that day). Fruits never graded 4 or above are
censored: their ``days_left`` is None and they are left out of forecast error.
"""

import os
from collections import defaultdict
from dataclasses import dataclass

END_OF_SHELF_LIFE = 4
SHEET = "Avocado Ripening Dataset.xlsx"


@dataclass
class AvocadoPhoto:
    file: str               # file name relative to the dataset folder
    group: str              # T10, T20 or Tam (room temperature)
    fruit_id: str           # group + sample number
    day: int                # day of the experiment
    side: str               # "a" or "b" (opposite sides of the fruit)
    stage: int              # ripening index 1 (underripe) .. 5 (overripe)
    days_left: int | None   # days until the fruit first reached stage 4; None if it never did


def label_days_left(photos: list[AvocadoPhoto]) -> None:
    end_day = {}
    for p in photos:
        if p.stage >= END_OF_SHELF_LIFE:
            end_day[p.fruit_id] = min(end_day.get(p.fruit_id, p.day), p.day)
    for p in photos:
        end = end_day.get(p.fruit_id)
        p.days_left = None if end is None else max(0, end - p.day)


def rows_to_photos(rows) -> list[AvocadoPhoto]:
    photos = []
    for name, _stamp, group, sample, day, stage, *_ in rows:
        if not name or stage is None:
            continue
        side = str(name).split("_")[3]
        photos.append(AvocadoPhoto(f"{name}.jpg", str(group), f"{group}-{int(sample):03d}", int(day), side, int(stage), None))
    label_days_left(photos)
    return photos


def load_photos(root: str) -> list[AvocadoPhoto]:
    import openpyxl

    wb = openpyxl.load_workbook(os.path.join(root, SHEET), read_only=True)
    rows = list(wb.worksheets[0].iter_rows(min_row=2, values_only=True))
    return rows_to_photos(rows)


def by_fruit(photos: list[AvocadoPhoto]) -> dict[str, list[AvocadoPhoto]]:
    out = defaultdict(list)
    for p in photos:
        out[p.fruit_id].append(p)
    return dict(out)

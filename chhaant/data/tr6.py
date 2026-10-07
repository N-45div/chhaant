"""TriModal Ripeness 6 (TR-6) as inspection sessions.

TR-6 (figshare 30783827, CC BY 4.0) photographs each fruit once per day: one
top-down shot, then 16 shots circling the fruit from roughly 40 degrees above.
The underside is never photographed. ``kaggle/prep/prep.py`` writes the
manifest this module reads.

TR-6 follows ONE physical fruit per produce type (checked by eye: the same
spots and stems recur), photographed in up to three sessions a day: morning,
midday and evening. A *session* is one 17-photo pass. Within a session photos
are seconds to minutes apart; sessions are hours apart, so a 30 minute gap
separates them cleanly. ``slot`` is the session's order within its day.

Six fruits make TR-6 good for multi-view questions and ripening trajectories,
but far too few to measure how well a forecast generalises across fruits.
"""

import csv
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

SESSION_GAP_S = 30 * 60
VIEWS_PER_SESSION = 17
SIDE_VIEWS = 16

# These were photographed for 47-72 days at 26-35 C before their first spoiled
# label, and the stem scar changes shape between dates: the fruit was most likely
# swapped without a label. Their time-to-spoil labels are not used; their
# sessions are still fine for single-session (multi-view) questions.
IDENTITY_UNCERTAIN = {"Tomato", "Indian_Gooseberry"}


@dataclass
class Session:
    fruit: str              # produce type, e.g. "Tomato"
    date: str               # YYYYMMDD
    day: int                # 1-based day index within this produce type
    slot: int               # 1-based order of this session within its day
    files: list[str]        # photo paths relative to the data root, in shooting order
    spoiled: int            # dataset label for the whole session (labels never vary within one)
    temp_c: float | None    # mean of the session's thermal-camera min/max readings
    fruit_id: str = ""      # the physical fruit (one per produce type in TR-6)
    hours_in_life: float = 0.0  # hours since this fruit's first session
    hours_to_spoiled: float | None = None  # hours until its first spoiled session; 0 if spoiled now
    extra: dict = field(default_factory=dict)

    @property
    def taken_at(self) -> datetime:
        return _stamp(self.files[0])

    @property
    def top_view(self) -> str:
        return self.files[0]

    @property
    def side_views(self) -> list[str]:
        return self.files[1:]

    def side_azimuths(self) -> list[float]:
        """Nominal azimuth of each side view: evenly spaced around the fruit."""
        n = len(self.side_views)
        return [360.0 * i / max(n, 1) for i in range(n)]


def _stamp(path: str) -> datetime:
    return datetime.strptime(os.path.basename(path)[:15], "%Y%m%d_%H%M%S")


def _split_oversized(run: list[dict]) -> list[list[dict]]:
    """Two fruits shot back to back show up as one run of ~34 photos: cut at the widest gaps."""
    parts = max(1, round(len(run) / VIEWS_PER_SESSION))
    if parts == 1:
        return [run]
    gaps = sorted(range(1, len(run)), key=lambda i: (_stamp(run[i]["file"]) - _stamp(run[i - 1]["file"])).total_seconds())
    cuts = sorted(gaps[-(parts - 1):])
    return [run[a:b] for a, b in zip([0, *cuts], [*cuts, len(run)])]


def _time_runs(day_rows: list[dict]) -> list[list[dict]]:
    """Split one day's photos of a fruit wherever the camera paused for over 30 minutes."""
    day_rows = sorted(day_rows, key=lambda r: _stamp(r["file"]))
    runs, cur = [], [day_rows[0]]
    for a, b in zip(day_rows, day_rows[1:]):
        if (_stamp(b["file"]) - _stamp(a["file"])).total_seconds() > SESSION_GAP_S:
            runs.append(cur)
            cur = []
        cur.append(b)
    runs.append(cur)
    return [part for run in runs for part in _split_oversized(run)]


def _temp(rows: list[dict]) -> float | None:
    vals = [(float(r["temp_min_c"]) + float(r["temp_max_c"])) / 2 for r in rows if r["temp_min_c"] and r["temp_max_c"]]
    return round(sum(vals) / len(vals), 2) if vals else None


def group_sessions(rows: list[dict]) -> list[Session]:
    """Turn manifest rows into sessions, then link sessions of the same fruit across days."""
    by_day = defaultdict(list)
    for r in rows:
        by_day[(r["fruit"], r["date"])].append(r)

    sessions = []
    for (fruit, date), day_rows in sorted(by_day.items()):
        for slot, run in enumerate(_time_runs(day_rows), 1):
            labels = {int(r["spoiled"]) for r in run if r["spoiled"] != ""}
            sessions.append(Session(
                fruit=fruit, date=date, day=int(run[0]["day"]), slot=slot,
                files=[r["file"] for r in run], spoiled=max(labels) if labels else 0, temp_c=_temp(run),
            ))
    _link_fruits(sessions)
    return sessions


def _link_fruits(sessions: list[Session]) -> None:
    """Order each produce type's sessions in time. A spoiled-to-fresh flip means a new fruit."""
    by_type = defaultdict(list)
    for s in sessions:
        by_type[s.fruit].append(s)
    for fruit, seq in by_type.items():
        seq.sort(key=lambda s: s.taken_at)
        batch, start, prev = 1, seq[0].taken_at, None
        for s in seq:
            if prev is not None and prev.spoiled == 1 and s.spoiled == 0:
                batch, start = batch + 1, s.taken_at
            s.fruit_id = f"{fruit}-{batch}"
            s.hours_in_life = round((s.taken_at - start).total_seconds() / 3600, 2)
            prev = s
        if fruit in IDENTITY_UNCERTAIN:
            continue
        for fid in {s.fruit_id for s in seq}:
            life = [s for s in seq if s.fruit_id == fid]
            first_bad = next((s.taken_at for s in life if s.spoiled), None)
            for s in life:
                s.hours_to_spoiled = None if first_bad is None else round(max(0.0, (first_bad - s.taken_at).total_seconds() / 3600), 2)


def load_sessions(data_root: str) -> list[Session]:
    with open(os.path.join(data_root, "tr6_manifest.csv"), newline="") as fh:
        return group_sessions(list(csv.DictReader(fh)))

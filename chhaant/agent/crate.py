"""A crate of real produce for the agent to work through.

TR-6 items carry a recorded 16-angle session (inspected by rotate-until-sure);
avocado items carry the dataset's two side photos for one day (their shelf
life comes from the validated forecaster). Each item has a hidden ``truth``
used only to score runs afterwards; the agent never sees it.
"""

import random
from dataclasses import dataclass, field

from chhaant.data.avocado import load_photos
from chhaant.data.tr6 import load_sessions
from chhaant.decide.route import RIPE_WINDOW_DAYS


@dataclass
class CrateItem:
    item_id: str
    produce: str
    kind: str                     # "tr6" or "avocado"
    temp_c: float                 # storage temperature
    session: object = None        # TR-6 Session
    photos: list[str] = field(default_factory=list)  # avocado photo paths, relative to the avocado root
    truth: dict = field(default_factory=dict)        # {"defective": bool, "days_left": float | None}

    def ok_to_pack(self, eat_in_days: float | None) -> bool:
        """Ground truth: is this item fit for an order eaten in ``eat_in_days``?

        Sound, still good on the day, and (for produce eaten ripe) ready by then.
        """
        if self.truth.get("defective"):
            return False
        left = self.truth.get("days_left")
        if eat_in_days is None or left is None:
            return True
        return eat_in_days <= left <= eat_in_days + RIPE_WINDOW_DAYS


def tr6_items(data_root: str, picks: list[tuple[str, int]], seed: int = 0) -> list[CrateItem]:
    """``picks``: (produce, spoiled 0/1) per item, drawn at random from TR-6's 16-view sessions."""
    rng = random.Random(seed)
    sessions = [s for s in load_sessions(data_root) if len(s.side_views) == 16]
    items, used = [], set()
    for n, (produce, spoiled) in enumerate(picks, 1):
        pool = [s for s in sessions if s.fruit == produce and s.spoiled == spoiled and id(s) not in used]
        s = rng.choice(pool)
        used.add(id(s))
        items.append(CrateItem(f"{produce[0]}{n}", produce, "tr6", s.temp_c or 30.0, session=s,
                               truth={"defective": bool(s.spoiled), "days_left": None}))
    return items


def avocado_items(data_root: str, days_left: list[int], seed: int = 0) -> list[CrateItem]:
    """One avocado per requested true days-left value, from the 20 C and room-temperature groups."""
    rng = random.Random(seed)
    by_day = {}
    for p in load_photos(data_root):
        if p.group in ("T20", "Tam") and p.days_left is not None:
            by_day.setdefault((p.fruit_id, p.day), []).append(p)
    pairs = [v for v in by_day.values() if len(v) == 2]
    items, used = [], set()
    for n, left in enumerate(days_left, 1):
        pool = [v for v in pairs if v[0].days_left == left and v[0].fruit_id not in used]
        pair = rng.choice(pool)
        used.add(pair[0].fruit_id)
        stage = max(p.stage for p in pair)
        items.append(CrateItem(f"A{n}", "Avocado", "avocado", 20.0, photos=[p.file for p in pair],
                               truth={"defective": stage >= 5, "days_left": float(left), "stage": stage}))
    return items

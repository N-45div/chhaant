"""Questions the robot puts to a person, and their answers.

The agent may ask a person instead of guessing (an undecided inspection, a
shelf life that straddles the eat-by day). A request stays pending until
someone answers it. Some moves (packing an undecided item, discarding a sound
one) are refused until a person has approved them.

``SimulatedReviewer`` answers from the dataset's own labels so whole runs can
be scored without a human in the loop; anything it answers is marked
``by="simulated reviewer"`` so it is never mistaken for a real person.
``PersonReviewer`` is the real thing: the agent waits while a person answers
in the web app, and a question nobody answers in time stays pending.

Several items can be put to a person in one review (a batch): every request in
it is shown at once and answered item by item, and each answer still covers
only its own item (and, for packing, its own order line).
"""

import itertools
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Request:
    id: str
    item_id: str
    kind: str                 # "pack", "reject" or "question"
    question: str
    evidence: dict
    status: str = "pending"   # "pending", "approved", "declined"
    answer: str = ""
    by: str = ""
    asked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    answered_at: str = ""
    order_line: int | None = None  # for "pack": the line it may be packed into, and only that one
    batch: str | None = None       # requests a person reviews together, in one glance


class ApprovalQueue:
    def __init__(self):
        self.requests: list[Request] = []
        self._ids = itertools.count(1)
        self._batches = itertools.count(1)

    def new_batch(self) -> str:
        return f"B{next(self._batches)}"

    def ask(self, item_id: str, kind: str, question: str, evidence: dict, order_line: int | None = None,
            batch: str | None = None) -> Request:
        if kind not in ("pack", "reject", "question"):
            raise ValueError(f"unknown request kind: {kind}")
        req = Request(f"Q{next(self._ids)}", item_id, kind, question, evidence, order_line=order_line, batch=batch)
        self.requests.append(req)
        return req

    def answer(self, request_id: str, approved: bool, answer: str, by: str) -> Request:
        req = self.get(request_id)
        if req.status != "pending":
            raise RuntimeError(f"{request_id} was already answered")
        req.status = "approved" if approved else "declined"
        req.answer, req.by = answer, by
        req.answered_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return req

    def get(self, request_id: str) -> Request:
        for r in self.requests:
            if r.id == request_id:
                return r
        raise KeyError(request_id)

    def approved(self, item_id: str, kind: str, order_line: int | None = None) -> bool:
        """An approval covers its own item and kind, and a pack approval only its own order line."""
        return any(r.item_id == item_id and r.kind == kind and r.status == "approved"
                   and (order_line is None or r.order_line == order_line) for r in self.requests)

    @property
    def pending(self) -> list[Request]:
        return [r for r in self.requests if r.status == "pending"]

    @property
    def reviews(self) -> int:
        """How many times a person was interrupted: one per batch, one per lone request."""
        return len({r.batch or r.id for r in self.requests})


class SimulatedReviewer:
    """Answers from ground truth, for scoring runs offline. Never presented as a person."""

    name = "simulated reviewer"

    def review(self, req: Request, truth_ok_to_pack: bool, truth_defective: bool | None = None) -> tuple[bool, str]:
        if req.kind == "pack":
            return truth_ok_to_pack, "fine to pack" if truth_ok_to_pack else "do not pack this one"
        if req.kind == "reject":  # discard only what is spoiled; a sound item that suits no line goes back
            spoiled = (not truth_ok_to_pack) if truth_defective is None else truth_defective
            return spoiled, "discard it" if spoiled else "keep it, it is sound: put it back in the crate"
        return True, "fine to pack" if truth_ok_to_pack else "not fit for this order"

    def review_many(self, reqs: list[Request], truths: list[tuple[bool, bool | None]]) -> list[tuple[bool, str]]:
        return [self.review(r, ok, bad) for r, (ok, bad) in zip(reqs, truths)]


class PersonReviewer:
    """A real person answering through the web app. The agent waits up to ``timeout_s``."""

    name = "person"

    def __init__(self, timeout_s: float = 300.0):
        self.timeout_s = timeout_s
        self._waiting: dict[str, list] = {}
        self._lock = threading.Lock()

    def review(self, req: Request, truth_ok_to_pack: bool, truth_defective: bool | None = None) -> tuple[bool, str] | None:
        """Block the agent until a person answers ``req``; None if nobody answers in time."""
        return self.review_many([req], [(truth_ok_to_pack, truth_defective)])[0]

    def review_many(self, reqs: list[Request], truths=None) -> list[tuple[bool, str] | None]:
        """Show every request at once, then wait until each is answered (one shared deadline)."""
        slots = [[threading.Event(), None] for _ in reqs]
        with self._lock:
            for req, slot in zip(reqs, slots):
                self._waiting[req.id] = slot
        deadline = time.monotonic() + self.timeout_s
        for slot in slots:
            slot[0].wait(max(0.0, deadline - time.monotonic()))
        with self._lock:
            for req in reqs:
                self._waiting.pop(req.id, None)
        return [slot[1] if slot[0].is_set() else None for slot in slots]

    def answer(self, request_id: str, approved: bool, answer: str) -> bool:
        """Called by the web app; False if nothing is waiting on that request."""
        with self._lock:
            slot = self._waiting.get(request_id)
            if slot is None:
                return False
            slot[1] = (bool(approved), answer)
            slot[0].set()
        return True

    @property
    def waiting(self) -> list[str]:
        with self._lock:
            return list(self._waiting)

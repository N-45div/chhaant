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
"""

import itertools
import threading
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


class ApprovalQueue:
    def __init__(self):
        self.requests: list[Request] = []
        self._ids = itertools.count(1)

    def ask(self, item_id: str, kind: str, question: str, evidence: dict, order_line: int | None = None) -> Request:
        if kind not in ("pack", "reject", "question"):
            raise ValueError(f"unknown request kind: {kind}")
        req = Request(f"Q{next(self._ids)}", item_id, kind, question, evidence, order_line=order_line)
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


class SimulatedReviewer:
    """Answers from ground truth, for scoring runs offline. Never presented as a person."""

    name = "simulated reviewer"

    def review(self, req: Request, truth_ok_to_pack: bool) -> tuple[bool, str]:
        if req.kind == "pack":
            return truth_ok_to_pack, "fine to pack" if truth_ok_to_pack else "do not pack this one"
        if req.kind == "reject":
            return not truth_ok_to_pack, "discard it" if not truth_ok_to_pack else "keep it, it is fine"
        return True, "fine to pack" if truth_ok_to_pack else "not fit for this order"


class PersonReviewer:
    """A real person answering through the web app. The agent waits up to ``timeout_s``."""

    name = "person"

    def __init__(self, timeout_s: float = 300.0):
        self.timeout_s = timeout_s
        self._waiting: dict[str, list] = {}
        self._lock = threading.Lock()

    def review(self, req: Request, truth_ok_to_pack: bool) -> tuple[bool, str] | None:
        """Block the agent until a person answers ``req``; None if nobody answers in time."""
        done = threading.Event()
        with self._lock:
            self._waiting[req.id] = [done, None]
        answered = done.wait(self.timeout_s)
        with self._lock:
            slot = self._waiting.pop(req.id, [done, None])
        return slot[1] if answered else None

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
